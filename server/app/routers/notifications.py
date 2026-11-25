from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "unread": db.query(Notification).filter(
            Notification.user_id == user.id, Notification.is_read == False  # noqa: E712
        ).count(),
        "items": [
            {
                "id": n.id, "title": n.title, "body": n.body,
                "order_id": n.order_id, "is_read": n.is_read,
                "created_at": n.created_at,
            }
            for n in q
        ],
    }


@router.post("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read == False  # noqa: E712
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
