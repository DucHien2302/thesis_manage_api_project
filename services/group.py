from sqlalchemy.orm import Session
from models.model import Group, GroupMember, Information, Invite, StudentInfo, Thesis
from schemas.group import (
    GroupCreate, GroupUpdate, GroupMemberCreate, 
    GroupWithMembersResponse, MemberDetailResponse
)
from uuid import UUID
from fastapi import HTTPException, status
from typing import List

def is_member_of_any_group(db: Session, user_id: UUID):
    """Kiểm tra người dùng đã thuộc nhóm nào chưa"""
    return db.query(GroupMember).filter(GroupMember.student_id == user_id).first() is not None

def create_group(db: Session, group: GroupCreate, user_id: UUID):
    """Tạo nhóm mới và đặt người tạo làm nhóm trưởng"""
    is_existing_member = db.query(GroupMember).filter(GroupMember.student_id == user_id).first()
    if is_existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn đã là thành viên của một nhóm khác, không thể tạo nhóm mới."
        )

    new_group = Group(name=group.name, leader_id=user_id, quantity=1)
    db.add(new_group)
    db.flush()
    db.refresh(new_group)

    group_leader = GroupMember(
        group_id=new_group.id,
        student_id=user_id,
        is_leader=True,
    )
    db.add(group_leader)
    db.commit()
    return new_group

def add_member(db: Session, group_id: UUID, member: GroupMemberCreate, leader_id: UUID):
    """Thêm thành viên vào nhóm (chỉ nhóm trưởng). Hàm này dành cho trường hợp thêm trực tiếp, không qua lời mời."""
    # 1. Kiểm tra nhóm và quyền của người gọi
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")
    if group.leader_id != leader_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ nhóm trưởng mới có quyền thêm thành viên.")

    # 2. Kiểm tra giới hạn thành viên
    if group.quantity >= 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nhóm đã đủ số lượng thành viên.")

    # 3. Kiểm tra xem người được thêm đã ở trong nhóm khác chưa
    if is_member_of_any_group(db, member.student_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thành viên này đã ở trong một nhóm khác.")
        
    # 4. Thêm thành viên
    new_member = GroupMember(group_id=group_id, student_id=member.student_id, is_leader=False)
    db.add(new_member)
    
    # 5. Cập nhật số lượng
    group.quantity += 1
    db.commit()
    db.refresh(new_member)
    return new_member

def remove_member(db: Session, group_id: UUID, member_id: UUID, leader_id: UUID):
    """Xóa thành viên khỏi nhóm (chỉ nhóm trưởng)"""
    # 1. Kiểm tra nhóm và quyền của người gọi
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")
    if group.leader_id != leader_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ nhóm trưởng mới có quyền xóa thành viên.")

    # 2. Không cho phép xóa chính nhóm trưởng
    if member_id == leader_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không thể xóa nhóm trưởng. Hãy chuyển quyền trước.")

    # 3. Tìm và xóa thành viên
    member_to_remove = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.student_id == member_id
    ).first()

    if not member_to_remove:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thành viên này trong nhóm.")
    
    db.delete(member_to_remove)
    
    # 4. Cập nhật số lượng
    group.quantity -= 1
    db.commit()
    return {"message": "Xóa thành viên thành công."}

def get_members(db: Session, group_id: UUID):
    """Lấy danh sách thành viên của nhóm"""
    return db.query(GroupMember).filter(GroupMember.group_id == group_id).all()

def transfer_leader(db: Session, group_id: UUID, new_leader_id: UUID, current_leader_id: UUID):
    """Chuyển quyền nhóm trưởng"""
    # 1. Kiểm tra nhóm và quyền của người gọi
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")
    if group.leader_id != current_leader_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ nhóm trưởng hiện tại mới có thể chuyển quyền.")

    # 2. Tìm thành viên cũ và mới
    current_leader_member = db.query(GroupMember).filter(GroupMember.student_id == current_leader_id, GroupMember.group_id == group_id).first()
    new_leader_member = db.query(GroupMember).filter(GroupMember.student_id == new_leader_id, GroupMember.group_id == group_id).first()

    if not new_leader_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người được chuyển quyền không phải là thành viên của nhóm.")

    # 3. Cập nhật quyền
    current_leader_member.is_leader = False
    new_leader_member.is_leader = True
    group.leader_id = new_leader_id
    
    db.commit()
    return {"message": "Chuyển quyền nhóm trưởng thành công."}


def get_all_groups_for_user(db: Session, user_id: UUID) -> List[GroupWithMembersResponse]:
    """
    Lấy thông tin TẤT CẢ các nhóm và danh sách thành viên của một user cụ thể.
    """
    user_memberships = db.query(GroupMember).filter(GroupMember.student_id == user_id).all()

    if not user_memberships:
        return []

    all_groups_list: List[GroupWithMembersResponse] = []
    
    for membership in user_memberships:
        group_id = membership.group_id
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            continue

        all_members_in_group = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()

        member_details_list: List[MemberDetailResponse] = []
        for member in all_members_in_group:
            student_user_id = member.student_id
            info = db.query(Information).filter(Information.user_id == student_user_id).first()
            student_info = db.query(StudentInfo).filter(StudentInfo.user_id == student_user_id).first()

            if info and student_info:
                member_obj = MemberDetailResponse(
                    user_id=student_user_id,
                    full_name=f"{info.last_name} {info.first_name}",
                    student_code=student_info.student_code,
                    is_leader=member.is_leader or False
                )
                member_details_list.append(member_obj)

        group_obj = GroupWithMembersResponse(
            id=group.id,
            name=group.name,
            leader_id=group.leader_id,
            members=member_details_list
        )
        all_groups_list.append(group_obj)

    return all_groups_list

def update_group_name(db: Session, group_id: UUID, new_name: str, user_id: UUID):
    """Cập nhật tên của một nhóm (chỉ nhóm trưởng)"""
    # 1. Tìm nhóm trong CSDL
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")

    # 2. Kiểm tra quyền: người thực hiện phải là nhóm trưởng
    if group.leader_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ nhóm trưởng mới có quyền đổi tên nhóm.")

    # 3. Cập nhật tên mới
    group.name = new_name
    db.commit()
    db.refresh(group)
    
    return group

def get_detailed_members_of_group(db: Session, group_id: UUID) -> List[MemberDetailResponse]:
    """Lấy danh sách thành viên chi tiết của một nhóm."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")

    all_members_in_group = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    
    member_details_list: List[MemberDetailResponse] = []
    for member in all_members_in_group:
        student_user_id = member.student_id
        info = db.query(Information).filter(Information.user_id == student_user_id).first()
        student_info = db.query(StudentInfo).filter(StudentInfo.user_id == student_user_id).first()

        if info and student_info:
            member_obj = MemberDetailResponse(
                user_id=student_user_id,
                full_name=f"{info.last_name} {info.first_name}",
                student_code=student_info.student_code,
                is_leader=member.is_leader or False
            )
            member_details_list.append(member_obj)
            
    return member_details_list

# HÀM MỚI ĐỂ GỘP THÔNG TIN NHÓM VÀ THÀNH VIÊN
def get_group_with_detailed_members(db: Session, group_id: UUID) -> GroupWithMembersResponse:
    """Lấy thông tin chi tiết của nhóm và danh sách thành viên của nó."""
    # 1. Lấy thông tin cơ bản của nhóm
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")
        
    # 2. Lấy danh sách thành viên chi tiết
    members_list = get_detailed_members_of_group(db, group_id)
    
    # 3. Tạo đối tượng trả về hoàn chỉnh
    response = GroupWithMembersResponse(
        id=group.id,
        name=group.name,
        leader_id=group.leader_id,
        members=members_list
    )
    
    return response


def delete_group(db: Session, group_id: UUID, user_id: UUID):
    """Xóa một nhóm và các thông tin liên quan (chỉ nhóm trưởng)"""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")

    if group.leader_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ nhóm trưởng mới có quyền xóa nhóm.")

    if group.thesis_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không thể xóa nhóm đã được gán vào đề tài.")

    # ... (phần còn lại của logic xóa giữ nguyên) ...
    db.query(Invite).filter(Invite.group_id == group_id).delete(synchronize_session=False)
    db.query(GroupMember).filter(GroupMember.group_id == group_id).delete(synchronize_session=False)
    db.delete(group)
    db.commit()
    
    return {"message": "Đã xóa nhóm thành công."}

def register_thesis_for_group(db: Session, group_id: UUID, thesis_id: UUID, user_id: UUID):
    """Đăng ký một đề tài cho nhóm (chỉ nhóm trưởng)"""
    # 1. Kiểm tra nhóm và quyền nhóm trưởng
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhóm.")
    if group.leader_id != user_id:
        raise HTTPException(status_code=403, detail="Chỉ nhóm trưởng mới có quyền đăng ký đề tài.")
    if group.thesis_id:
        raise HTTPException(status_code=400, detail="Nhóm này đã đăng ký đề tài khác.")

    # 2. Kiểm tra đề tài
    thesis = db.query(Thesis).filter(Thesis.id == thesis_id).first()
    if not thesis:
        raise HTTPException(status_code=404, detail="Không tìm thấy đề tài.")
    
    # 3. Kiểm tra xem đề tài đã có nhóm nào đăng ký chưa
    is_thesis_taken = db.query(Group).filter(Group.thesis_id == thesis_id).first()
    if is_thesis_taken:
        raise HTTPException(status_code=400, detail="Đề tài này đã được nhóm khác đăng ký.")

    # 4. Gán đề tài cho nhóm và cập nhật trạng thái
    group.thesis_id = thesis_id
    thesis.status = 2 # Giả sử 2 là trạng thái "Đã đăng ký"
    
    db.commit()
    db.refresh(group)
    return group