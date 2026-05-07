"""
Keywords router — CRUD for tracked keywords.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.database import get_supabase

router = APIRouter(prefix="/keywords", tags=["keywords"])

Platform = Literal["x", "instagram", "facebook", "tiktok"]


class KeywordCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    platform: Platform
    active: bool = True


class KeywordUpdate(BaseModel):
    active: Optional[bool] = None


@router.get("/")
async def list_keywords(platform: Optional[Platform] = None):
    db = get_supabase()
    query = db.table("keywords").select("*").order("created_at", desc=True)
    if platform:
        query = query.eq("platform", platform)
    resp = query.execute()
    return {"keywords": resp.data}


@router.post("/", status_code=201)
async def create_keyword(body: KeywordCreate):
    db = get_supabase()
    # Check for duplicate
    existing = (
        db.table("keywords")
        .select("id")
        .eq("keyword", body.keyword)
        .eq("platform", body.platform)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Keyword already exists for this platform.")

    resp = (
        db.table("keywords")
        .insert(body.model_dump())
        .execute()
    )
    return {"keyword": resp.data[0]}


@router.patch("/{keyword_id}")
async def update_keyword(keyword_id: str, body: KeywordUpdate):
    db = get_supabase()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    resp = (
        db.table("keywords")
        .update(updates)
        .eq("id", keyword_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Keyword not found.")
    return {"keyword": resp.data[0]}


@router.delete("/{keyword_id}", status_code=204)
async def delete_keyword(keyword_id: str):
    db = get_supabase()
    db.table("keywords").delete().eq("id", keyword_id).execute()
    return None
