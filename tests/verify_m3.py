"""Stage 3 (Milestone 3 / Task 3.1) Verification Script: Local Document Indexer, Cited Q&A & Research Workflow."""

from __future__ import annotations

import httpx
from pathlib import Path
from _isolated import base_url  # refuses to run outside tests/run_tests.py

REPO_ROOT = Path(__file__).resolve().parent.parent  # project root, wherever Loki lives



def main() -> None:
    docs_dir = str(REPO_ROOT / "docs")
    with httpx.Client(base_url=base_url(), timeout=120.0) as c:
        # 1. Clear index first for a clean test
        c.post("/api/docs/clear")
        st0 = c.get("/api/docs/status").json()
        assert st0["indexed_files_count"] == 0
        print("1. CLEAN INDEX STATUS OK: 0 files, 0 chunks")

        # 2. Add & Index Loki's `docs/` folder
        add_res = c.post("/api/docs/folders", json={"folder_path": docs_dir}).json()
        assert add_res["ok"] is True
        assert add_res["files_indexed"] >= 5
        print(
            "2. INDEXED FOLDER OK:",
            add_res["folder_path"],
            "| Files:",
            add_res["files_indexed"],
            "| Chunks:",
            add_res["chunks_created"],
        )

        # 3. Deterministic Hybrid Search (TF-IDF + Keyword)
        srch = c.post(
            "/api/docs/search",
            json={"query": "Three-Switch Cloud Provider Gate ADR-004", "top_k": 3},
        ).json()
        assert srch["ok"] is True
        assert len(srch["results"]) > 0
        cites = [r["citation"] for r in srch["results"]]
        print("3. HYBRID SEARCH OK | Top Citations:", cites)

        # 4. Verify Pause Access Privacy Switch blocks both search and workflow
        p_on = c.post("/api/docs/pause", json={"paused": True}).json()
        assert p_on["indexing_paused"] is True
        blocked_srch = c.post(
            "/api/docs/search", json={"query": "Cloud Provider Gate", "top_k": 3}
        ).json()
        assert blocked_srch["ok"] is False and blocked_srch.get("paused") is True
        blocked_wf = c.post(
            "/api/workflows/run",
            json={
                "workflow_id": "folder_research_digest",
                "inputs": {"focus_question": "Summarize ADRs"},
                "wait": True,
            },
        ).json()["run"]
        assert blocked_wf["status"] == "failed"
        print("4. PAUSE ACCESS PRIVACY GATE OK:", blocked_wf["error"])

        # Resume access
        p_off = c.post("/api/docs/pause", json={"paused": False}).json()
        assert p_off["indexing_paused"] is False

        # 5. Verify Cited Document Q&A with local Ollama
        ask_res = c.post(
            "/api/docs/ask",
            json={
                "question": "Briefly list the 3 conditions required by the Cloud Provider Gate and cite the file.",
                "top_k": 3,
            },
        ).json()
        assert ask_res["ok"] is True
        assert ask_res["data_left_pc"] is False
        print("5. CITED DOCUMENT Q&A OK:")
        print("   Citations passed to model:", [x["citation"] for x in ask_res["citations"]])
        print("   Answer preview:", repr(ask_res["answer"][:300]))

        # 6. Verify `folder_research_digest` Workflow End-to-End
        wf_ok = c.post(
            "/api/workflows/run",
            json={
                "workflow_id": "folder_research_digest",
                "inputs": {
                    "focus_question": "Summarize the files stored in loki/data/ and cite the source lines."
                },
                "wait": True,
            },
        ).json()["run"]
        assert wf_ok["status"] == "completed"
        print(
            "6. FOLDER RESEARCH WORKFLOW OK:",
            wf_ok["run_id"],
            "| Step statuses:",
            {s["step_id"]: s["status"] for s in wf_ok["steps"]},
        )

        # 7. Verify Remove Single File & Re-Index Controls
        first_file = add_res["summary"]["indexed_files"][0]["file_path"]
        rem_file = c.post("/api/docs/files/remove", json={"file_path": first_file}).json()
        assert rem_file["summary"]["indexed_files_count"] == add_res["files_indexed"] - 1
        reidx = c.post("/api/docs/reindex").json()
        assert reidx["summary"]["indexed_files_count"] == add_res["files_indexed"]
        print(
            "7. REMOVE FILE & RE-INDEX CONTROLS OK: Count went",
            add_res["files_indexed"],
            "->",
            rem_file["summary"]["indexed_files_count"],
            "->",
            reidx["summary"]["indexed_files_count"],
        )

        # 8. Unload model from GPU VRAM after test
        un = c.post("/api/ollama/unload", json={}).json()
        print("8. VRAM UNLOADED AFTER TEST:", un["unloaded_models"])


if __name__ == "__main__":
    main()
