from datetime import datetime
from io import BytesIO
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from typing import List
from db.database import get_db
import pandas as pd
from models.model import Batch, Department, LecturerInfo, Major, User
from schemas.thesis import BatchResponse, BatchSimpleResponse, DepartmentResponse, MajorResponse, ThesisCreate, ThesisUpdate, ThesisResponse
from services.thesis import (
    create,
    get_all_batches_with_details,
    get_all_departments,
    get_all_majors,
    get_theses_by_batch_id,
    update_thesis,
    get_thesis_by_id,
    get_all_theses,
    delete_thesis
)
from pathlib import Path
from routers.auth import get_current_user
from uuid import UUID
from fastapi.responses import FileResponse
router = APIRouter(
    prefix="/theses",
    tags=["theses"]
)

@router.get("/download-template", summary="Tải file Excel mẫu")
def download_template():
    file_path = Path("static/thesis_template.xlsx")

    if not file_path.exists():
        data = {
            "STT": [],
            "TÊN ĐỀ TÀI": [],
            "NỘI DUNG YÊU CẦU": [],
            "LOẠI ĐỀ TÀI": [],
            "CHUYÊN NGÀNH": [], # <-- THÊM CỘT MỚI
            "MÃ GV HƯỚNG DẪN": [],
            "MÃ GV PHẢN BIỆN": [],
            "BỘ MÔN": [],
            "GHI CHÚ": []
        }
        df = pd.DataFrame(data)
        # Thêm một dòng ví dụ
        example_row = pd.DataFrame([{
            "STT": 1,
            "TÊN ĐỀ TÀI": "Hệ thống quản lý thư viện",
            "NỘI DUNG YÊU CẦU": "Xây dựng các chức năng chính...",
            "LOẠI ĐỀ TÀI": 2,
            "CHUYÊN NGÀNH": "Công nghệ thông tin", # Ví dụ
            "MÃ GV HƯỚNG DẪN": "GV01",
            "MÃ GV PHẢN BIỆN": "GV02",
            "BỘ MÔN": "KTPM",
            "GHI CHÚ": ""
        }])
        df = pd.concat([df, example_row], ignore_index=True)
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(file_path, index=False)

    return FileResponse(
        path=file_path,
        filename="thesis_template.xlsx",
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@router.post("/import--excel")
def import_thesis_from_simple_excel(
    file: UploadFile = File(...),
    # Chỉ giữ lại status là thông tin chung cho cả file
    status: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Import danh sách đề tài từ file Excel với logic nghiệp vụ đầy đủ.
    """
    # 1. Tự động tìm đợt (batch) mới nhất dựa vào ngày tạo
    latest_batch = db.query(Batch).order_by(Batch.create_datetime.desc()).first()
    if not latest_batch:
        raise HTTPException(status_code=404, detail="Không tìm thấy đợt học nào trong hệ thống.")

    content = file.file.read()
    # Header ở dòng 5 trong file excel mẫu, tương ứng với header=4 trong pandas
    df = pd.read_excel(BytesIO(content), header=5) 

    created_count = 0
    errors = []

    for i, row in df.iterrows():
        try:
            # Bỏ qua các dòng trống
            if pd.isna(row.get("STT")) or pd.isna(row.get("TÊN ĐỀ TÀI")):
                continue
            
            # 2. Xử lý Chuyên ngành (tìm kiếm theo tên)
            major_name_from_excel = row.get("CHUYÊN NGÀNH")
            if pd.isna(major_name_from_excel):
                raise Exception("Cột 'CHUYÊN NGÀNH' không được để trống.")
            major_name_to_find = str(major_name_from_excel).strip()
            major = db.query(Major).filter(Major.name == major_name_to_find).first()
            if not major:
                raise Exception(f"Chuyên ngành với tên '{major_name_to_find}' không tồn tại.")
            major_id_val = major.id

            # 3. Xử lý Giảng viên Hướng dẫn
            instructor_codes = [code.strip() for code in str(row.get("MÃ GV HƯỚNG DẪN", "")).split(',') if code.strip()]
            instructors = []
            if instructor_codes:
                instructors = db.query(LecturerInfo).filter(LecturerInfo.lecturer_code.in_(instructor_codes)).all()
                if len(instructors) != len(instructor_codes):
                    raise Exception(f"Một hoặc nhiều Mã GV Hướng Dẫn không tồn tại: {instructor_codes}")

            # 4. Xử lý Giảng viên Phản biện
            reviewer_codes = [code.strip() for code in str(row.get("MÃ GV PHẢN BIỆN", "")).split(',') if code.strip()]
            reviewers = []
            if reviewer_codes:
                reviewers = db.query(LecturerInfo).filter(LecturerInfo.lecturer_code.in_(reviewer_codes)).all()
                if len(reviewers) != len(reviewer_codes):
                    raise Exception(f"Một hoặc nhiều Mã GV Phản Biện không tồn tại: {reviewer_codes}")

            # 5. Xử lý Bộ môn (theo ID hoặc Tên)
            department_id = None
            dept_input = row.get("BỘ MÔN")
            if pd.notna(dept_input):
                if isinstance(dept_input, (int, float)):
                    department = db.query(Department).filter(Department.id == int(dept_input)).first()
                    if not department:
                        raise Exception(f"Bộ môn với ID '{int(dept_input)}' không tồn tại.")
                else:
                    department = db.query(Department).filter(Department.name == str(dept_input).strip()).first()
                    if not department:
                        raise Exception(f"Bộ môn với tên '{str(dept_input).strip()}' không tồn tại.")
                department_id = department.id
            
            # 6. Lấy "Loại đề tài" từ file Excel
            thesis_type_from_excel = row.get("LOẠI ĐỀ TÀI")
            if pd.isna(thesis_type_from_excel):
                raise Exception("Cột 'LOẠI ĐỀ TÀI' không được để trống.")
            try:
                thesis_type_val = int(thesis_type_from_excel)
                if thesis_type_val not in [1, 2]:
                     raise Exception(f"Giá trị '{thesis_type_val}' không hợp lệ cho Loại đề tài (chỉ 1 hoặc 2).")
            except (ValueError, TypeError):
                raise Exception(f"Giá trị '{thesis_type_from_excel}' không phải là số cho Loại đề tài.")
            
            # 7. Lấy Ghi chú
            notes_text = row.get("GHI CHÚ")

            # 8. Tạo đối tượng ThesisCreate
            thesis_data = ThesisCreate(
                title=row["TÊN ĐỀ TÀI"],
                description=row.get("NỘI DUNG YÊU CẦU", ""),
                notes=notes_text if pd.notna(notes_text) else None,
                thesis_type=thesis_type_val,
                status=status,
                major_id=major_id_val,
                department_id=department_id,
                batch_id=latest_batch.id,
                start_date=latest_batch.start_date,
                end_date=latest_batch.end_date,
                instructor_ids=[lec.user_id for lec in instructors],
                reviewer_ids=[rev.user_id for rev in reviewers]
            )

            create(db, thesis_data, user.id)
            created_count += 1

        except Exception as e:
            errors.append({
                "row": i + 6,
                "title": row.get("TÊN ĐỀ TÀI", "<trống>"),
                "error": str(e)
            })

    return {"success": created_count, "errors": errors}

@router.post("/", response_model=ThesisResponse)
def create_thesis_endpoint(
    thesis: ThesisCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    API để tạo mới một luận văn (thesis).
    """
    return create(db, thesis, user.id)

@router.put("/{thesis_id}", response_model=ThesisResponse)
def update_thesis_endpoint(
    thesis_id: UUID,
    thesis: ThesisUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    API để cập nhật thông tin một luận văn (thesis).
    Chỉ cho phép giảng viên tạo đề tài đó được sửa.
    """
    update_thesis(db, thesis_id, thesis, user.id)
    return get_thesis_by_id(db, thesis_id)



@router.get("/{thesis_id}", response_model=ThesisResponse)
def get_thesis_by_id_endpoint(thesis_id: UUID, db: Session = Depends(get_db)):
    """
    API để lấy thông tin một luận văn (thesis) theo ID.
    """
    return get_thesis_by_id(db, thesis_id)

@router.get("/", response_model=List[ThesisResponse])
def get_all_theses_endpoint(db: Session = Depends(get_db)):
    """
    API để lấy danh sách tất cả các luận văn (theses) với thông tin của tất cả giảng viên hướng dẫn.
    """
    return get_all_theses(db)

@router.delete("/{thesis_id}")
def delete_thesis_endpoint(
    thesis_id: UUID,
    db: Session = Depends(get_db)
):
    """
    API để xóa một luận văn (thesis) theo ID.
    """
    return delete_thesis(db, thesis_id)

@router.get("/getall/major", response_model=List[MajorResponse])
def get_all_majors_endpoint(db: Session = Depends(get_db)):
    """
    API để lấy danh sách tất cả chuyên ngành (major).
    """
    return get_all_majors(db)

@router.get("/getall/department/g", response_model=List[DepartmentResponse])
def get_all_departments_endpoint(db: Session = Depends(get_db)):
    """
    API để lấy danh sách tất cả khoa (department).
    """
    return get_all_departments(db)

@router.get("/by-batch/{batch_id}", response_model=List[ThesisResponse])
def get_theses_by_batch_endpoint(batch_id: UUID, db: Session = Depends(get_db)):
    """
    API lấy danh sách luận văn theo đợt (batch_id).
    """
    return get_theses_by_batch_id(db, batch_id)


@router.get("/getall/batches", response_model=List[BatchResponse])
def get_all_batches_endpoint(db: Session = Depends(get_db)):
    """
    API lấy danh sách các đợt (batch) kèm học kỳ và năm học, sắp xếp từ mới đến cũ.
    """
    return get_all_batches_with_details(db)