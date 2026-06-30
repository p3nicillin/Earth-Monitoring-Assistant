import { useMutation } from "@tanstack/react-query";
import { ArrowUp, Bot, Sparkles, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "../lib/api";

interface AssistantPanelProps {
  projectId?: string;
  open: boolean;
  onClose: () => void;
}

export function AssistantPanel({ projectId, open, onClose }: AssistantPanelProps) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Array<{ question: string; answer: string; count: number }>>([]);
  const ask = useMutation({
    mutationFn: (text: string) => api.ask(text, projectId),
    onSuccess: (result, text) => {
      setHistory((items) => [...items, { question: text, answer: result.answer, count: result.result_count }]);
      setQuestion("");
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const clean = question.trim();
    if (clean && !ask.isPending) ask.mutate(clean);
  }

  return (
    <aside
      className={`assistant-panel ${open ? "assistant-open" : ""}`}
      aria-hidden={!open}
      inert={open ? undefined : true}
    >
      <header>
        <div className="assistant-icon"><Sparkles size={17} /></div>
        <div><strong>Terra Assistant</strong><span>GROUNDED IN PROJECT EVENTS</span></div>
        <button onClick={onClose} aria-label="Close assistant"><X size={18} /></button>
      </header>
      <div className="assistant-thread">
        <div className="assistant-welcome">
          <Bot size={24} />
          <strong>What would you like to investigate?</strong>
          <p>I translate questions into scoped geospatial filters. I won’t invent detections outside your data.</p>
        </div>
        {history.map((item, index) => (
          <div className="exchange" key={`${item.question}-${index}`}>
            <p className="user-message">{item.question}</p>
            <div className="assistant-message"><Sparkles size={14} /><p>{item.answer}<small>{item.count} mapped results</small></p></div>
          </div>
        ))}
        {ask.isError && <div className="assistant-error">{ask.error.message}</div>}
      </div>
      <div className="prompt-chips">
        {["Show floods this week", "Critical events today", "Where is vegetation changing?"].map((prompt) => (
          <button key={prompt} onClick={() => setQuestion(prompt)}>{prompt}</button>
        ))}
      </div>
      <form className="assistant-input" onSubmit={submit}>
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about detected change…" />
        <button disabled={!question.trim() || ask.isPending} aria-label="Send question"><ArrowUp size={17} /></button>
      </form>
    </aside>
  );
}
