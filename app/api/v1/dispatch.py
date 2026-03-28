from __future__ import annotations

from fastapi import APIRouter

from app.schemas.dashboard import DispatchTeamOut

router = APIRouter()


@router.get('/dispatch-teams', response_model=list[DispatchTeamOut])
async def list_dispatch_teams() -> list[DispatchTeamOut]:
    return [
        DispatchTeamOut(id='t1', name='Đội 1 - Trung tâm', district='Quận 1', status='available', capacity=8),
        DispatchTeamOut(id='t2', name='Đội 2 - Bắc', district='Quận Bình Thạnh', status='available', capacity=6),
        DispatchTeamOut(id='t3', name='Đội 3 - Nam', district='Quận 7', status='busy', capacity=10),
        DispatchTeamOut(id='t4', name='Đội 4 - Đông', district='Quận Thủ Đức', status='en_route', capacity=7),
        DispatchTeamOut(id='t5', name='Đội 5 - Tây', district='Quận Bình Tân', status='available', capacity=9),
    ]
