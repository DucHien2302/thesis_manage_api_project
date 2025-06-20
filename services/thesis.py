from datetime import datetime
import uuid
from fastapi import HTTPException,status
from sqlalchemy import UUID, or_
from sqlalchemy.orm import Session
from models.model import AcademyYear, Batch, Department, Information, LecturerInfo, Major, Semester, Thesis, ThesisLecturer, User
from schemas.thesis import AcademyYearResponse, BatchResponse, BatchSimpleResponse, DepartmentResponse, InstructorResponse, SemesterResponse, ThesisCreate, ThesisResponse, ThesisUpdate

def create(db: Session, thesis: ThesisCreate, lecturer_id: uuid.UUID):
    """
    Tạo một đề tài mới với các quy tắc nghiệp vụ:
    - Chỉ giảng viên hoặc admin được tạo.
    - Nếu thesis_type=2 (Đồ án), phải có ít nhất một người phản biện.
    - Hỗ trợ nhiều giảng viên hướng dẫn và nhiều giảng viên phản biện.
    """
    # 1. Kiểm tra quyền người tạo (phải là Giảng viên hoặc Admin)
    creator = db.query(User).filter(User.id == lecturer_id, or_(User.user_type == 3, User.user_type == 1)).first()
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Chỉ giảng viên hoặc admin mới có quyền tạo đề tài."
        )

    # 2. Kiểm tra nghiệp vụ: Nếu là Đồ án (type=2), danh sách phản biện không được rỗng
    if thesis.thesis_type == 2 and not thesis.reviewer_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Với loại đề tài là Đồ án, phải có ít nhất một giảng viên phản biện."
        )

    # 3. Kiểm tra tất cả giảng viên được gán (hướng dẫn và phản biện) có hợp lệ không
    all_lecturer_ids = set(thesis.instructor_ids)
    if thesis.reviewer_ids:
        all_lecturer_ids.update(thesis.reviewer_ids)
    
    if all_lecturer_ids: # Chỉ kiểm tra nếu có ID nào được cung cấp
        valid_lecturers = db.query(User).filter(User.id.in_(all_lecturer_ids), User.user_type == 3).all()
        if len(valid_lecturers) != len(all_lecturer_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Một hoặc nhiều ID giảng viên/phản biện không hợp lệ hoặc không phải là giảng viên."
            )

    # 4. Kiểm tra bộ môn (department) có hợp lệ không
    if thesis.department_id:
        department = db.query(Department).filter(Department.id == thesis.department_id).first()
        if not department:
            raise HTTPException(status_code=400, detail=f"Bộ môn với ID {thesis.department_id} không tồn tại.")

    # 5. Tạo đối tượng Thesis trong database
    db_thesis = Thesis(
        title=thesis.title,
        description=thesis.description,
        thesis_type=thesis.thesis_type,
        start_date=thesis.start_date,
        end_date=thesis.end_date,
        status=thesis.status,
        create_by=lecturer_id,
        batch_id=thesis.batch_id,
        major_id=thesis.major_id,
        notes=thesis.notes,
        department_id=thesis.department_id
    )
    db.add(db_thesis)
    db.commit()
    db.refresh(db_thesis)
    
    # 6. Gán vai trò cho các giảng viên trong bảng ThesisLecturer
    # Gán vai trò Giảng viên hướng dẫn (role = 1)
    if thesis.instructor_ids:
        for l_id in thesis.instructor_ids:
            db.add(ThesisLecturer(lecturer_id=l_id, thesis_id=db_thesis.id, role=1))

    # Gán vai trò Giảng viên phản biện (role = 2)
    if thesis.reviewer_ids:
        for r_id in thesis.reviewer_ids:
            db.add(ThesisLecturer(lecturer_id=r_id, thesis_id=db_thesis.id, role=2))

    db.commit()

    # 7. Trả về thông tin chi tiết của đề tài vừa tạo
    return get_thesis_by_id(db, db_thesis.id)

def update_thesis(db: Session, thesis_id: UUID, thesis: ThesisUpdate, user_id: UUID):
    db_thesis = db.query(Thesis).filter(Thesis.id == thesis_id).first()
    if not db_thesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thesis not found"
        )
    update_data = thesis.dict(exclude_unset=True)
    if "batch_id" in update_data:
        batch = db.query(Batch).filter(Batch.id == update_data["batch_id"]).first()
        if not batch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid batch ID"
            )

    # ✅ Nếu có lecturer_ids, kiểm tra và cập nhật
    if "lecturer_ids" in update_data:
        lecturer_ids = update_data.pop("lecturer_ids")
        # Kiểm tra tính hợp lệ
        valid_lecturers = db.query(User).filter(User.id.in_(lecturer_ids), User.user_type == 3).all()
        if len(valid_lecturers) != len(lecturer_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Một hoặc nhiều giảng viên không hợp lệ hoặc không tồn tại"
            )

        # Xoá toàn bộ giảng viên cũ
        db.query(ThesisLecturer).filter(ThesisLecturer.thesis_id == thesis_id).delete()

        # Thêm giảng viên mới
        for l_id in lecturer_ids:
            db.add(ThesisLecturer(
                lecturer_id=l_id,
                thesis_id=thesis_id,
                role=1  # Mặc định
            ))

    # Cập nhật các trường còn lại
    for key, value in update_data.items():
        setattr(db_thesis, key, value)

    db_thesis.update_datetime = datetime.utcnow()
    db.commit()
    db.refresh(db_thesis)
    return get_thesis_by_id(db, db_thesis.id)

def get_thesis_by_id(db: Session, thesis_id: UUID) -> ThesisResponse:
    thesis = db.query(Thesis).filter(Thesis.id == thesis_id).first()
    if not thesis:
        raise HTTPException(status_code=404, detail="Không tìm thấy đề tài.")

    thesis_lecturers = db.query(ThesisLecturer).filter(ThesisLecturer.thesis_id == thesis.id).all()
    
    # --- THAY ĐỔI LOGIC TẠI ĐÂY ---
    instructors_list = []
    reviewers_list = [] # Chuyển thành danh sách

    for tl in thesis_lecturers:
        lecturer_info = db.query(LecturerInfo).filter(LecturerInfo.user_id == tl.lecturer_id).first()
        if lecturer_info:
            user_info = db.query(Information).filter(Information.user_id == lecturer_info.user_id).first()
            department = db.query(Department).filter(Department.id == lecturer_info.department).first()
            
            if user_info:
                lecturer_details = InstructorResponse(
                    name=f"{user_info.last_name} {user_info.first_name}",
                    email=lecturer_info.email,
                    department=lecturer_info.department,
                    lecturer_code=lecturer_info.lecturer_code,
                    department_name=department.name if department else None
                )
                # Phân loại vai trò
                if tl.role == 1:
                    instructors_list.append(lecturer_details)
                elif tl.role == 2:
                    reviewers_list.append(lecturer_details) # Thêm vào danh sách

    # --- Lấy các thông tin liên quan khác ---
    batch_response = None
    batch = db.query(Batch).filter(Batch.id == thesis.batch_id).first()
    if batch:
        semester_response = None
        semester = db.query(Semester).filter(Semester.id == batch.semester_id).first()
        if semester:
            academy_year_response = None
            academy_year = db.query(AcademyYear).filter(AcademyYear.id == semester.academy_year_id).first()
            if academy_year:
                academy_year_response = AcademyYearResponse.from_orm(academy_year)
            semester_response = SemesterResponse(id=semester.id, name=semester.name, start_date=semester.start_date, end_date=semester.end_date, academy_year=academy_year_response)
        batch_response = BatchResponse(id=batch.id, name=batch.name, start_date=batch.start_date, end_date=batch.end_date, semester=semester_response)
        
    major = db.query(Major).filter(Major.id == thesis.major_id).first()
    major_name = major.name if major else "Chuyên ngành không xác định"
    
    department_response = None
    if thesis.department_id:
        dept_model = db.query(Department).filter(Department.id == thesis.department_id).first()
        if dept_model:
            department_response = DepartmentResponse.from_orm(dept_model)

    # --- Tạo đối tượng trả về hoàn chỉnh ---
    return ThesisResponse(
        id=thesis.id,
        thesis_type=thesis.thesis_type,
        status=(
            "Từ chối" if thesis.status == 0 else
            "Chưa được đăng ký" if thesis.status == 1 else
            "Đã đăng ký" if thesis.status == 2 else
            "Chờ duyệt" if thesis.status == 3 else
            "Đã hoàn thành" if thesis.status == 4 else
            "Hủy đăng ký" if thesis.status == 5 else
            "Không xác định"
        ),
        name=thesis.title,
        description=thesis.description,
        start_date=thesis.start_date,
        end_date=thesis.end_date,
        notes=thesis.notes,
        reason=thesis.reason,
        instructors=instructors_list,
        reviewers=reviewers_list, # Trả về danh sách GVPB
        department=department_response,
        name_thesis_type="Khóa luận" if thesis.thesis_type == 1 else "Đồ án",
        batch=batch_response,
        major=major_name
    )

def get_all_theses(db: Session) -> list[ThesisResponse]:
    theses = db.query(Thesis).order_by(Thesis.create_datetime.desc()).all()
    thesis_responses = []
    for thesis in theses:
        thesis_lecturers = db.query(ThesisLecturer).filter(ThesisLecturer.thesis_id == thesis.id).all()
        instructors_list = []
        reviewers_list = []

        for tl in thesis_lecturers:
            lecturer_info = db.query(LecturerInfo).filter(LecturerInfo.user_id == tl.lecturer_id).first()
            if lecturer_info:
                user_info = db.query(Information).filter(Information.user_id == lecturer_info.user_id).first()
                department = db.query(Department).filter(Department.id == lecturer_info.department).first()

                if user_info:
                    lecturer_details = InstructorResponse(
                        name=f"{user_info.last_name} {user_info.first_name}",
                        email=lecturer_info.email,
                        lecturer_code=lecturer_info.lecturer_code,
                        department=lecturer_info.department,
                        department_name=department.name if department else None
                    )
                    # Phân loại vai trò
                    if tl.role == 1:  # Giảng viên hướng dẫn
                        instructors_list.append(lecturer_details)
                    elif tl.role == 2:  # Giảng viên phản biện
                        reviewers_list.append(lecturer_details)
        batch = db.query(Batch).filter(Batch.id == thesis.batch_id).first()
        semester = db.query(Semester).filter(Semester.id == batch.semester_id).first() if batch else None
        academy_year = db.query(AcademyYear).filter(AcademyYear.id == semester.academy_year_id).first() if semester else None
        major = db.query(Major).filter(Major.id == thesis.major_id).first()
        major_name = major.name if major else "Chuyên ngành không xác định"
        department_response = None
        if thesis.department_id:
            department = db.query(Department).filter(Department.id == thesis.department_id).first()
            if department:
                department_response = DepartmentResponse.from_orm(department)

        thesis_responses.append(ThesisResponse(
            id=thesis.id,
            thesis_type=thesis.thesis_type,
            status=(
                "Từ chối" if thesis.status == 0 else
                "Chờ duyệt" if thesis.status == 1 else
                "Đã duyệt cấp bộ môn" if thesis.status == 2 else
                "Đã duyệt cấp khoa" if thesis.status == 3 else
                "Chưa được đăng ký" if thesis.status == 4 else
                "Đã được đăng ký" if thesis.status == 5 else
                "Không xác định"
            ),
            reason=thesis.reason,
            name=thesis.title,
            description=thesis.description,
            start_date=thesis.start_date,
            end_date=thesis.end_date,
            instructors=instructors_list, # Trả về danh sách GVHD
            reviewers=reviewers_list,   
            department=department_response,
            name_thesis_type="Khóa luận" if thesis.thesis_type == 1 else "Đồ án",
            batch={
                "id": batch.id,
                "name": batch.name,
                "start_date": batch.start_date,
                "end_date": batch.end_date,
                "semester": {
                    "id": semester.id,
                    "name": semester.name,
                    "start_date": semester.start_date,
                    "end_date": semester.end_date,
                    "academy_year": {
                        "id": academy_year.id,
                        "name": academy_year.name,
                        "start_date": academy_year.start_date,
                        "end_date": academy_year.end_date
                    } if academy_year else None
                } if semester else None
            } if batch else None,
            major=major_name
        ))

    return thesis_responses


def delete_thesis(db: Session, thesis_id: UUID):
    """
    Xóa một luận văn (thesis).
    """
    db_thesis = db.query(Thesis).filter(Thesis.id == thesis_id).first()
    if not db_thesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thesis not found"
        )
    db.delete(db_thesis)
    db.commit()
    return {"message": "Thesis deleted successfully"}

def get_all_majors(db: Session):
    return db.query(Major).all()

def get_all_departments(db: Session):
    return db.query(Department).all()

def get_theses_by_batch_id(db: Session, batch_id: UUID) -> list[ThesisResponse]:
    theses = db.query(Thesis).filter(Thesis.batch_id == batch_id).order_by(Thesis.create_datetime.desc()).all()
    results = []

    for thesis in theses:
        thesis_lecturers = db.query(ThesisLecturer).filter(ThesisLecturer.thesis_id == thesis.id).all()
        instructors = []
        for tl in thesis_lecturers:
            lecturer_info = db.query(LecturerInfo).filter(LecturerInfo.user_id == tl.lecturer_id).first()
            if lecturer_info:
                user_info = db.query(Information).filter(Information.user_id == lecturer_info.user_id).first()
                department_name = None
                if lecturer_info.department:
                    dept = db.query(Department).filter(Department.id == lecturer_info.department).first()
                    department_name = dept.name if dept else None

                if user_info:
                    instructors.append({
                        "name": f"{user_info.last_name} {user_info.first_name} ",
                        "email": lecturer_info.email,
                        "lecturer_code": lecturer_info.lecturer_code,
                        "department": lecturer_info.department,
                        "department_name": department_name
                    })

        batch = db.query(Batch).filter(Batch.id == thesis.batch_id).first()
        semester = db.query(Semester).filter(Semester.id == batch.semester_id).first() if batch else None
        academy_year = db.query(AcademyYear).filter(AcademyYear.id == semester.academy_year_id).first() if semester else None
        major = db.query(Major).filter(Major.id == thesis.major_id).first()
        major_name = major.name if major else "Chuyên ngành không xác định"

        results.append(ThesisResponse(
            id=thesis.id,
            thesis_type=thesis.thesis_type,
            status=(
                "Từ chối" if thesis.status == 0 else
                "Chờ duyệt" if thesis.status == 1 else
                "Đã duyệt cấp bộ môn" if thesis.status == 2 else
                "Đã duyệt cấp khoa" if thesis.status == 3 else
                "Chưa được đăng ký" if thesis.status == 4 else
                "Đã được đăng ký" if thesis.status == 5 else
                "Không xác định"
            ),
            reason=thesis.reason,
            name=thesis.title,
            description=thesis.description,
            start_date=thesis.start_date,
            end_date=thesis.end_date,
            instructors=instructors,
            name_thesis_type="Khóa luận" if thesis.thesis_type == 1 else "Đồ án",
            batch={
                "id": batch.id,
                "name": batch.name,
                "start_date": batch.start_date,
                "end_date": batch.end_date,
                "semester": {
                    "id": semester.id,
                    "name": semester.name,
                    "start_date": semester.start_date,
                    "end_date": semester.end_date,
                    "academy_year": {
                        "id": academy_year.id,
                        "name": academy_year.name,
                        "start_date": academy_year.start_date,
                        "end_date": academy_year.end_date
                    } if academy_year else None
                } if semester else None
            } if batch else None,
            major=major_name
        ))

    return results


def get_all_batches_with_details(db: Session) -> list[BatchResponse]:
    batches = db.query(Batch).order_by(Batch.create_datetime.desc()).all()
    results = []

    for batch in batches:
        semester = db.query(Semester).filter(Semester.id == batch.semester_id).first()
        academy_year = db.query(AcademyYear).filter(AcademyYear.id == semester.academy_year_id).first() if semester else None

        results.append(BatchResponse(
            id=batch.id,
            name=batch.name,
            start_date=batch.start_date,
            end_date=batch.end_date,
            semester=SemesterResponse(
                id=semester.id,
                name=semester.name,
                start_date=semester.start_date,
                end_date=semester.end_date,
                academy_year=AcademyYearResponse(
                    id=academy_year.id,
                    name=academy_year.name,
                    start_date=academy_year.start_date,
                    end_date=academy_year.end_date
                ) if academy_year else None
            ) if semester else None
        ))

    return results
