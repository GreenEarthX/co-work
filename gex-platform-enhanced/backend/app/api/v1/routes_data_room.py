"""
GEX Bankability — Data Room API (v2.0)

Endpoints:
  GET  /api/v1/data-room/{project_id}                    — Full ToC with categories
  GET  /api/v1/data-room/{project_id}/category/{cat_id}  — Documents in a category
  POST /api/v1/data-room/{project_id}/documents          — Upload/register document
  GET  /api/v1/data-room/{project_id}/completeness       — Completeness score per category
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import hashlib

router = APIRouter()


class DocumentRegister(BaseModel):
    category_id: int
    name: str
    gate_ref: Optional[str] = None
    version: str = "v1"
    status: str = "UPLOADED"


def _demo_hash(doc_name: str) -> str:
    return hashlib.sha256(doc_name.encode()).hexdigest()


# Playbook Annex E — 11 categories
_CATEGORIES = [
    {"id": 1,  "name": "Corporate & Structure",       "doc_count": 3,  "completeness_pct": 95},
    {"id": 2,  "name": "Technical Documentation",      "doc_count": 5,  "completeness_pct": 78},
    {"id": 3,  "name": "Financial Model",              "doc_count": 4,  "completeness_pct": 82},
    {"id": 4,  "name": "Offtake & Commercial",         "doc_count": 3,  "completeness_pct": 70},
    {"id": 5,  "name": "EPC & Construction",           "doc_count": 4,  "completeness_pct": 55},
    {"id": 6,  "name": "Grid & Power",                 "doc_count": 3,  "completeness_pct": 60},
    {"id": 7,  "name": "Permits & Environmental",      "doc_count": 4,  "completeness_pct": 88},
    {"id": 8,  "name": "Insurance",                    "doc_count": 3,  "completeness_pct": 45},
    {"id": 9,  "name": "Certification & GoOs",         "doc_count": 3,  "completeness_pct": 65},
    {"id": 10, "name": "Legal & Regulatory",           "doc_count": 3,  "completeness_pct": 50},
    {"id": 11, "name": "Evidence Index",               "doc_count": 2,  "completeness_pct": 90},
]


@router.get("/{project_id}")
async def get_data_room(project_id: str):
    """Full data room table of contents for a project."""
    total_docs = sum(c["doc_count"] for c in _CATEGORIES)
    weighted_completeness = sum(c["completeness_pct"] * c["doc_count"] for c in _CATEGORIES) // total_docs
    return {
        "project_id": project_id,
        "categories": _CATEGORIES,
        "overall_completeness_pct": weighted_completeness,
        "total_documents": total_docs,
        "verified_documents": int(total_docs * 0.6),
    }


@router.get("/{project_id}/category/{cat_id}")
async def get_category_documents(project_id: str, cat_id: int):
    """Documents in a specific data room category."""
    cat = next((c for c in _CATEGORIES if c["id"] == cat_id), None)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category {cat_id} not found")

    # Generate demo docs based on category
    doc_templates = {
        1: ["Corporate Structure Chart v2.pdf", "Articles of Incorporation.pdf", "Shareholder Agreement v3.pdf"],
        2: ["FEED Study - Front End Engineering v2.pdf", "Process Flow Diagram rev4.dwg", "Equipment List v3.xlsx", "HAZOP Report - Final.pdf", "Electrolyser Performance Spec.pdf"],
        3: ["Financial Model - PF Engine Run 2026-03-15.xlsx", "Auditor Financial Model Review.pdf", "DSCR Sensitivity Analysis.xlsx", "Reserve Account Sizing.pdf"],
        4: ["Offtake Agreement - GRTgaz v3.pdf", "PPA Agreement - EDF Renewables.pdf", "Logistics MOU - Dunkerque Port.pdf"],
        5: ["EPC Contract - Technip Energies v3.pdf", "EPC Performance Bond.pdf", "OEM Technical Specification - Nel.pdf", "Construction Programme Q1-2026.pdf"],
        6: ["Grid Connection Agreement - RTE v2.pdf", "Electrical Single Line Diagram.pdf", "Grid Capacity Reservation Letter.pdf"],
        7: ["EIA Approval - DREAL Normandie.pdf", "Building Permit BP-2025-1247.pdf", "Water Rights Permit.pdf", "ICPE Authorization.pdf"],
        8: ["CAR Policy Schedule - AXA XL.pdf", "DSU Quotation - Allianz.pdf", "Lender Loss Payee Endorsement.pdf"],
        9: ["RFNBO Pre-audit Report - DNV.pdf", "LCA Study - Bureau Veritas.pdf", "GoO Registry Application.pdf"],
        10: ["Senior Facility Agreement - Draft v2.pdf", "Security Package - Legal Opinion.pdf", "Regulatory Compliance Memo.pdf"],
        11: ["Evidence Index SHA-256 Chain.json", "Gate Completeness Summary.pdf"],
    }
    docs_names = doc_templates.get(cat_id, ["Document.pdf"])

    docs = [
        {
            "id": f"doc-{project_id}-cat{cat_id}-{i+1:03d}",
            "name": name,
            "gate_ref": f"G{min(cat_id, 11)}" if cat_id < 11 else None,
            "version": "v2" if i == 0 else "v1",
            "upload_date": "2026-03-10",
            "status": "VERIFIED" if i < 2 else ("UPLOADED" if i < 4 else "PENDING"),
            "hash": _demo_hash(f"{project_id}:{name}")[:8] + "...",
            "hash_full": _demo_hash(f"{project_id}:{name}"),
        }
        for i, name in enumerate(docs_names)
    ]

    return {
        "project_id": project_id,
        "category": cat,
        "documents": docs,
    }


@router.post("/{project_id}/documents")
async def register_document(project_id: str, doc: DocumentRegister):
    """Register/upload a document to the data room."""
    return {
        "registered": True,
        "document_id": f"doc-{project_id}-new",
        "project_id": project_id,
        "document": doc,
        "hash": _demo_hash(doc.name),
    }


@router.get("/{project_id}/completeness")
async def get_completeness(project_id: str):
    """Per-category completeness score."""
    return {
        "project_id": project_id,
        "categories": [
            {"id": c["id"], "name": c["name"], "completeness_pct": c["completeness_pct"]}
            for c in _CATEGORIES
        ],
        "overall_pct": sum(c["completeness_pct"] for c in _CATEGORIES) // len(_CATEGORIES),
    }
