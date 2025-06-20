from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class ThesisBase(BaseModel): 
    title: str
    description: str
    thesis_type: int
    start_date: datetime
    end_date: datetime
    status:  int
    batch_id: UUID
    major_id: UUID
    department_id: Optional[int] = None
    notes: Optional[str] = None

class ThesisCreate(ThesisBase):
    instructor_ids: List[UUID]
    reviewer_ids: Optional[List[UUID]] = []

class ThesisUpdate(BaseModel):
    title:  Optional[str] = None
    description:  Optional[str] = None
    thesis_type:  Optional[int] = None
    start_date: Optional[datetime] = None
    end_date:  Optional[datetime] = None
    status:  Optional[int] = None
    batch_id: Optional[UUID] = None
    major_id: Optional[UUID] = None
    lecturer_ids: Optional[List[UUID]] = None  #
    reason: Optional[str] = None

class InstructorResponse(BaseModel):
    name: str
    email: str
    lecturer_code: str
    department: int
    department_name: Optional[str] = None

class AcademyYearResponse(BaseModel):
    id: UUID
    name: str
    start_date: datetime
    end_date: datetime

    class Config:
        orm_mode = True

class SemesterResponse(BaseModel):
    id: UUID
    name: str
    start_date: datetime
    end_date: datetime
    academy_year: Optional[AcademyYearResponse] 

    class Config:
        orm_mode = True

class BatchResponse(BaseModel):
    id: UUID
    name: str
    start_date: datetime
    end_date: datetime
    semester: SemesterResponse  

    class Config:
        orm_mode = True

class MajorResponse(BaseModel):
    id: UUID
    name: str

    class Config:
        orm_mode = True

class DepartmentBase(BaseModel):
    name: str

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None

class DepartmentResponse(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True

class BatchSimpleResponse(BaseModel):
    id: UUID
    name: str
    start_date: datetime
    end_date: datetime

    class Config:
        orm_mode = True

class ThesisResponse(BaseModel):
    id: UUID
    thesis_type: int
    status: str
    name: str
    description: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    instructors: List[InstructorResponse]
    reviewers: List[InstructorResponse] = []
    batch: BatchResponse
    major: str
    department: Optional[DepartmentResponse] = None 
    reason: Optional[str]
    name_thesis_type: str
    notes: Optional[str]

    class Config:
        orm_mode = True




