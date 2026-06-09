from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, END

from app.config import Settings
from app.state import ShoppingState
from app.data_access import ShoppingDataStore, build_data_tools
from rag.embeddings import SentenceTransformerEmbeddings
from rag.vector_store import ChromaPolicyStore
from provider import get_chat_model
from app.utils import extract_json_payload, timestamp_utc
from app.prompts import (
    SUPERVISOR_PROMPT,
    POLICY_WORKER_PROMPT,
    DATA_WORKER_PROMPT,
    RESPONSE_WORKER_PROMPT,
)


class ShoppingAssistant:
    """Student scaffold.

    Mục tiêu:
    - Dùng `Settings` để load config.
    - Dùng provider trong `src/provider/`.
    - Dùng embedding loader thật trong `src/rag/embeddings.py`.
    - Tự hoàn thiện phần còn lại: graph, routing, tool calling, RAG search, response synthesis.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()

        # 1. load chat model từ provider tương ứng
        self.chat_model = get_chat_model(self.settings)

        # 2. load dataset order/customer
        self.store = ShoppingDataStore(self.settings.orders_path)

        # 3. load vector store cho policy
        self.embedding_model = SentenceTransformerEmbeddings(self.settings.embedding_model_name)
        self.policy_store = ChromaPolicyStore(
            persist_directory=self.settings.chroma_dir,
            embedding_model=self.embedding_model,
        )
        self.policy_store.ensure_index(self.settings.policy_path)

        # 4. build worker tools
        self.data_tools = build_data_tools(self.store)
        self.data_tools_dict = {t.name: t for t in self.data_tools}

        # 5. compile LangGraph
        self.graph = build_graph(self)

    def ask(
        self,
        question: str,
        trace_file: Path | None = None,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        # 1. nếu rebuild_index=True thì rebuild Chroma collection
        if rebuild_index:
            self.policy_store.rebuild(self.settings.policy_path)

        # 2. invoke graph với state ban đầu
        initial_state: ShoppingState = {
            "question": question,
            "trace": [],
        }

        final_state = self.graph.invoke(initial_state)

        # Prepare outputs
        payload = {
            "route": final_state.get("route", {}),
            "policy_result": final_state.get("policy_result", {}),
            "data_result": final_state.get("data_result", {}),
            "final_answer": final_state.get("final_answer", ""),
            "trace": final_state.get("trace", []),
        }

        # 3. lưu trace ra JSON nếu trace_file được cung cấp
        if trace_file:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(payload["trace"], f, ensure_ascii=False, indent=2)

        return payload

    def run_batch(
        self,
        test_file: Path,
        output_dir: Path,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.policy_store.rebuild(self.settings.policy_path)

        if not test_file.exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")

        with open(test_file, "r", encoding="utf-8") as f:
            test_cases = json.load(f)

        output_dir.mkdir(parents=True, exist_ok=True)
        traces_dir = output_dir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for case in test_cases:
            case_id = case.get("id", "unknown")
            question = case.get("question", "")
            
            trace_file_path = traces_dir / f"{case_id}_trace.json"
            res = self.ask(question, trace_file=trace_file_path)

            # Extract final answer status for summary
            ans = res["final_answer"]
            status = "ok"
            if "status: clarification_needed" in ans.lower():
                status = "clarification_needed"
            elif "status: not_found" in ans.lower():
                status = "not_found"

            results.append({
                "id": case_id,
                "question": question,
                "route": res["route"],
                "status": status,
                "final_answer": ans,
            })

        summary = {
            "timestamp": timestamp_utc(),
            "total_cases": len(test_cases),
            "results": results,
        }

        summary_file = output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        return summary


def build_graph(assistant: ShoppingAssistant) -> Any:
    workflow = StateGraph(ShoppingState)

    def supervisor_node(state: ShoppingState) -> dict[str, Any]:
        question = state["question"]
        messages = [
            SystemMessage(content=SUPERVISOR_PROMPT),
            HumanMessage(content=question),
        ]
        response = assistant.chat_model.invoke(messages)
        content = str(response.content)
        route = extract_json_payload(content)
        if not route:
            route = {
                "status": "ok",
                "needs_policy": True,
                "needs_data": True,
                "clarification_question": None,
            }
        trace_entry = {
            "node": "supervisor",
            "timestamp": timestamp_utc(),
            "input": {"question": question},
            "output": route,
        }
        return {
            "route": route,
            "trace": [trace_entry],
        }

    def worker_1_policy_node(state: ShoppingState) -> dict[str, Any]:
        question = state["question"]
        hits = assistant.policy_store.search(question, top_k=assistant.settings.top_k)
        context_parts = []
        for i, hit in enumerate(hits):
            context_parts.append(
                f"--- Chunk {i+1} ---\n"
                f"Citation: {hit['citation']}\n"
                f"Content:\n{hit['content']}\n"
            )
        rag_context = "\n".join(context_parts)
        prompt = POLICY_WORKER_PROMPT.format(rag_context=rag_context)
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=question),
        ]
        response = assistant.chat_model.invoke(messages)
        content = str(response.content)
        policy_result = extract_json_payload(content)
        if not policy_result:
            policy_result = {
                "status": "ok",
                "summary": content,
                "facts": [],
                "citations": [hit["citation"] for hit in hits] if hits else [],
            }
        trace_entry = {
            "node": "worker_1_policy",
            "timestamp": timestamp_utc(),
            "input": {"question": question, "hits_count": len(hits)},
            "output": policy_result,
        }
        return {
            "policy_result": policy_result,
            "trace": [trace_entry],
        }

    def worker_2_data_node(state: ShoppingState) -> dict[str, Any]:
        question = state["question"]
        messages = [
            SystemMessage(
                content="Bạn là chuyên gia tra cứu dữ liệu. Bạn PHẢI sử dụng các công cụ (tools) tra cứu "
                        "đơn hàng, khách hàng, hoặc voucher nếu cần thiết để trả lời câu hỏi. "
                        "Hãy gọi công cụ thích hợp dựa trên tham số có trong câu hỏi."
            ),
            HumanMessage(content=question),
        ]
        model_with_tools = assistant.chat_model.bind_tools(assistant.data_tools)
        tool_calls_executed = []

        for _ in range(3):
            res = model_with_tools.invoke(messages)
            messages.append(res)
            if not res.tool_calls:
                break

            for tc in res.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id = tc["id"]
                tool_calls_executed.append({
                    "name": tool_name,
                    "args": tool_args,
                })
                if tool_name in assistant.data_tools_dict:
                    tool_obj = assistant.data_tools_dict[tool_name]
                    tool_output = tool_obj.invoke(tool_args)
                else:
                    tool_output = {"status": "error", "message": f"Tool {tool_name} not found"}
                messages.append(ToolMessage(
                    content=json.dumps(tool_output, ensure_ascii=False),
                    name=tool_name,
                    tool_call_id=tool_id,
                ))

        summary_prompt = DATA_WORKER_PROMPT.format(
            database_context=json.dumps([m.content for m in messages if isinstance(m, ToolMessage)], ensure_ascii=False, indent=2)
        )
        messages_summary = [
            SystemMessage(content=summary_prompt),
            HumanMessage(content=f"Tóm tắt kết quả tra cứu cho câu hỏi: {question}"),
        ]
        res_summary = assistant.chat_model.invoke(messages_summary)
        content = str(res_summary.content)
        data_result = extract_json_payload(content)
        if not data_result:
            data_result = {
                "status": "ok",
                "summary": content,
                "facts": [],
                "missing_fields": [],
                "not_found_entities": [],
            }

        # Scan for not_found returns in tool responses
        for m in messages:
            if isinstance(m, ToolMessage):
                try:
                    payload = json.loads(m.content)
                    if payload.get("status") == "not_found":
                        data_result["status"] = "not_found"
                        for k, v in payload.items():
                            if k != "status":
                                entity_desc = f"{k} {v}"
                                if entity_desc not in data_result.setdefault("not_found_entities", []):
                                    data_result["not_found_entities"].append(entity_desc)
                except Exception:
                    pass

        trace_entry = {
            "node": "worker_2_data",
            "timestamp": timestamp_utc(),
            "input": {"question": question},
            "tool_calls": tool_calls_executed,
            "output": data_result,
        }
        return {
            "data_result": data_result,
            "trace": [trace_entry],
        }

    def worker_3_response_node(state: ShoppingState) -> dict[str, Any]:
        question = state["question"]
        route = state.get("route", {})
        policy_result = state.get("policy_result", {})
        data_result = state.get("data_result", {})

        prompt = RESPONSE_WORKER_PROMPT.format(
            user_question=question,
            supervisor_route=json.dumps(route, ensure_ascii=False, indent=2),
            policy_result=json.dumps(policy_result, ensure_ascii=False, indent=2),
            data_result=json.dumps(data_result, ensure_ascii=False, indent=2),
        )
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Hãy tạo câu trả lời cuối cùng theo đúng định dạng mẫu."),
        ]
        response = assistant.chat_model.invoke(messages)
        final_answer = str(response.content).strip()

        # Resilient Formatting Check
        lower_ans = final_answer.lower()
        if not (lower_ans.startswith("answer:") or lower_ans.startswith("status: clarification_needed") or lower_ans.startswith("status: not_found")):
            if route.get("status") == "clarification_needed" or data_result.get("status") == "clarification_needed":
                q = route.get("clarification_question") or "Vui lòng cung cấp thêm thông tin."
                final_answer = f"Status: clarification_needed\nQuestion: {q}"
            elif data_result.get("status") == "not_found":
                msg = f"Không tìm thấy thông tin liên quan."
                if data_result.get("not_found_entities"):
                    msg = f"Không tìm thấy thông tin cho {', '.join(data_result['not_found_entities'])}."
                final_answer = f"Status: not_found\nMessage: {msg}"
            else:
                summary_pol = policy_result.get("summary", "")
                summary_dat = data_result.get("summary", "")
                citations = policy_result.get("citations", [])
                facts_dat = "\n".join([f"- {f}" for f in data_result.get("facts", [])])

                final_answer = f"Answer: {summary_pol} {summary_dat}\n\nEvidence:\n"
                if citations:
                    final_answer += f"- Policy: {', '.join(citations)}\n"
                else:
                    final_answer += f"- Policy: Không có trích dẫn chính sách cụ thể.\n"
                if facts_dat:
                    final_answer += f"- Order data:\n{facts_dat}"
                else:
                    final_answer += f"- Order data: Không có dữ liệu đơn hàng liên quan."

        trace_entry = {
            "node": "worker_3_response",
            "timestamp": timestamp_utc(),
            "input": {
                "route": route,
                "policy_result": policy_result,
                "data_result": data_result,
            },
            "output": {"final_answer": final_answer},
        }
        return {
            "final_answer": final_answer,
            "trace": [trace_entry],
        }

    # Add Nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("worker_1_policy", worker_1_policy_node)
    workflow.add_node("worker_2_data", worker_2_data_node)
    workflow.add_node("worker_3_response", worker_3_response_node)

    # Set Entry Point
    workflow.set_entry_point("supervisor")

    # Routing Function
    def route_after_supervisor(state: ShoppingState) -> list[str] | str:
        route = state.get("route", {})
        if route.get("status") == "clarification_needed":
            return "worker_3_response"
        dests = []
        if route.get("needs_policy"):
            dests.append("worker_1_policy")
        if route.get("needs_data"):
            dests.append("worker_2_data")
        if not dests:
            return "worker_3_response"
        return dests

    # Add Conditional Edges
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "worker_1_policy": "worker_1_policy",
            "worker_2_data": "worker_2_data",
            "worker_3_response": "worker_3_response",
        },
    )

    # Add Normal Edges
    workflow.add_edge("worker_1_policy", "worker_3_response")
    workflow.add_edge("worker_2_data", "worker_3_response")
    workflow.add_edge("worker_3_response", END)

    return workflow.compile()
