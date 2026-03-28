from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.schemas.dashboard import AHPPresetOut

router = APIRouter()

CRITERIA = ['danger_level', 'num_people', 'vulnerable_groups', 'waiting_time', 'accessibility']

PRESETS = [
    AHPPresetOut(
        id='balanced',
        label='Cân bằng',
        description='Ưu tiên nhẹ cho mức độ nguy hiểm nhưng vẫn giữ các tiêu chí còn lại cân bằng.',
        matrix=[
            [1, 2, 2, 2, 3],
            [0.5, 1, 1, 2, 2],
            [0.5, 1, 1, 2, 2],
            [0.5, 0.5, 0.5, 1, 2],
            [1 / 3, 0.5, 0.5, 0.5, 1],
        ],
    ),
    AHPPresetOut(
        id='vulnerable-first',
        label='Ưu tiên người dễ bị tổn thương',
        description='Đẩy cao trọng số cho nhóm dễ bị tổn thương như trẻ em, người già, phụ nữ mang thai.',
        matrix=[
            [1, 1, 1 / 3, 2, 2],
            [1, 1, 1 / 3, 2, 2],
            [3, 3, 1, 4, 4],
            [0.5, 0.5, 0.25, 1, 2],
            [0.5, 0.5, 0.25, 0.5, 1],
        ],
    ),
    AHPPresetOut(
        id='mass-rescue',
        label='Ưu tiên số lượng',
        description='Ưu tiên ca có nhiều người mắc kẹt để tối ưu năng lực cứu hộ hàng loạt.',
        matrix=[
            [1, 0.5, 2, 2, 3],
            [2, 1, 3, 4, 4],
            [0.5, 1 / 3, 1, 2, 2],
            [0.5, 0.25, 0.5, 1, 2],
            [1 / 3, 0.25, 0.5, 0.5, 1],
        ],
    ),
]


def get_presets() -> list[AHPPresetOut]:
    return PRESETS


@router.get('/presets', response_model=list[AHPPresetOut])
async def list_presets() -> list[AHPPresetOut]:
    return get_presets()
