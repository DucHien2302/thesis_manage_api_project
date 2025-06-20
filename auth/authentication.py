from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import jwt
from typing import Optional

from sqlalchemy import select
from models.model import SysFunction, SysRoleFunction, SysUserRole
from sqlalchemy.orm import Session
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in enviroment variables")
if not ALGORITHM:
    raise ValueError("ALGORITHM must be set in enviroment variables")

def get_user_functions(db: Session, user_id: str) -> list[str]:
    role_ids_select = select(SysUserRole.role_id).filter(SysUserRole.user_id == user_id)
    function_paths = (
        db.query(SysFunction.path)
        .join(SysRoleFunction, SysFunction.id == SysRoleFunction.function_id)
        .filter(
            SysRoleFunction.role_id.in_(role_ids_select),
            SysFunction.parent_id == None,
            SysFunction.status == 1,
            SysRoleFunction.status == 1
        )
        .distinct()
        .all()
    )
    return [f.path for f in function_paths if f.path]


# def create_access_token(user_id: str, user_name: str, expires_delta: Optional[timedelta] = None):
#     to_encode = {"uuid": user_id, "name": user_name}
#     expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})

#     encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
#     if isinstance(encoded_jwt, bytes):
#         encoded_jwt = encoded_jwt.decode("utf-8")  # ✅ quan trọng

#     return encoded_jwt
def create_access_token(user_id: str, user_name: str, user_type: int, db: Session, expires_delta: Optional[timedelta] = None):
    user_functions = get_user_functions(db, user_id)

    to_encode = {
        "uuid": user_id,
        "name": user_name,
        "type": user_type, 
        "functions": user_functions  # ✅ Thêm vào token
    }

    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    if isinstance(encoded_jwt, bytes):
        encoded_jwt = encoded_jwt.decode("utf-8")

    return encoded_jwt

def create_refresh_token(user_id: str, user_name: str, expires_delta: Optional[timedelta] = None):
    to_encode = {"uuid": user_id, "name": user_name}
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else: 
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt