/**
 * TeamAlignmentPanel — threaded discussion for a specific component.
 *
 * Replaces the legacy "Notes" textarea with a back-and-forth conversation
 * scoped to a single canvas node. Supports two inline mention syntaxes:
 *
 *   @name      → tags a teammate (resolved against team_users)
 *   (field)    → references a parameter/field on the same component
 *
 * Messages are persisted in localStorage under `gex_team_alignment` keyed by
 * componentId. Mentioned users also receive a stub notification through the
 * existing `gex_role_notifications` channel so the new alignment thread plugs
 * into the same downstream inbox surface as ownership assignments.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { AtSign, MessageSquare, Send, Tag } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useTeamData, type TeamUserRow } from "@/hooks/useTeamData";

interface AlignmentMessage {
  id: string;
  author: string;
  body: string;
  mentions: string[]; // user ids
  fieldRefs: string[]; // field names
  created_at: string;
}

interface Props {
  componentId: string;
  componentLabel?: string;
  /** Field names that can be referenced via `(field)` syntax. */
  fieldNames?: string[];
  /** Logged-in author name shown next to messages. */
  currentAuthor?: string;
}

const STORAGE_KEY = "gex_team_alignment";

function loadAll(): Record<string, AlignmentMessage[]> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveAll(map: Record<string, AlignmentMessage[]>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* ignore quota errors */
  }
}

function pushAlignmentNotification(payload: {
  user_id: string;
  component_id: string;
  message_id: string;
  author: string;
  excerpt: string;
}) {
  try {
    const raw = localStorage.getItem("gex_role_notifications");
    const list = raw ? JSON.parse(raw) : [];
    list.push({ ...payload, kind: "alignment_mention", at: new Date().toISOString() });
    localStorage.setItem("gex_role_notifications", JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

/** Render a message body, highlighting @user and (field) tokens. */
function renderBody(body: string, users: TeamUserRow[], fieldNames: string[]) {
  // Match @word or (anything until matching close paren without nested parens)
  const parts: Array<{ type: "text" | "user" | "field"; value: string }> = [];
  const re = /(@[\p{L}0-9_.-]+)|(\([^()]+\))/gu;
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    if (m.index > lastIndex) parts.push({ type: "text", value: body.slice(lastIndex, m.index) });
    if (m[1]) parts.push({ type: "user", value: m[1] });
    else if (m[2]) parts.push({ type: "field", value: m[2] });
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < body.length) parts.push({ type: "text", value: body.slice(lastIndex) });

  return parts.map((p, i) => {
    if (p.type === "user") {
      const name = p.value.slice(1).toLowerCase();
      const matched = users.find(
        (u) => u.full_name.toLowerCase().split(/\s+/).join(".") === name
          || u.full_name.toLowerCase().split(/\s+/)[0] === name
          || u.email.toLowerCase().split("@")[0] === name,
      );
      return (
        <span
          key={i}
          className={`inline-flex items-center gap-0.5 rounded px-1 py-px text-[11px] font-medium ${
            matched
              ? "bg-primary/12 text-primary"
              : "bg-muted text-muted-foreground"
          }`}
          title={matched?.email}
        >
          {p.value}
        </span>
      );
    }
    if (p.type === "field") {
      const inside = p.value.slice(1, -1).trim();
      const matched = fieldNames.find((f) => f.toLowerCase() === inside.toLowerCase());
      return (
        <span
          key={i}
          className={`inline-flex items-center gap-0.5 rounded px-1 py-px text-[11px] font-mono ${
            matched
              ? "bg-accent/40 text-foreground ring-1 ring-accent"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {p.value}
        </span>
      );
    }
    return <span key={i}>{p.value}</span>;
  });
}

/** Find the active token (@... or (... ) under the caret. */
function getActiveToken(value: string, caret: number): { kind: "user" | "field"; query: string; start: number } | null {
  const before = value.slice(0, caret);
  // user mention: last @ not separated by whitespace or close
  const atIdx = before.lastIndexOf("@");
  const parenIdx = before.lastIndexOf("(");
  const closeParen = before.lastIndexOf(")");

  // Active field ref if `(` exists after last `)`
  if (parenIdx > closeParen) {
    const query = before.slice(parenIdx + 1);
    if (!query.includes("\n")) {
      return { kind: "field", query, start: parenIdx };
    }
  }
  if (atIdx > -1) {
    const query = before.slice(atIdx + 1);
    if (!/\s/.test(query) && query.length <= 40) {
      return { kind: "user", query, start: atIdx };
    }
  }
  return null;
}

const TeamAlignmentPanel = ({
  componentId,
  componentLabel,
  fieldNames = [],
  currentAuthor = "You",
}: Props) => {
  const { users } = useTeamData();
  const [messages, setMessages] = useState<AlignmentMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [caret, setCaret] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load thread for this component
  useEffect(() => {
    const all = loadAll();
    setMessages(all[componentId] || []);
  }, [componentId]);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  const activeToken = useMemo(() => getActiveToken(draft, caret), [draft, caret]);

  const userSuggestions = useMemo(() => {
    if (activeToken?.kind !== "user") return [];
    const q = activeToken.query.toLowerCase();
    return users
      .filter((u) =>
        u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
      )
      .slice(0, 6);
  }, [activeToken, users]);

  const fieldSuggestions = useMemo(() => {
    if (activeToken?.kind !== "field") return [];
    const q = activeToken.query.toLowerCase();
    return fieldNames.filter((f) => f.toLowerCase().includes(q)).slice(0, 6);
  }, [activeToken, fieldNames]);

  const insertSuggestion = (kind: "user" | "field", value: string) => {
    if (!activeToken) return;
    const before = draft.slice(0, activeToken.start);
    const after = draft.slice(caret);
    const insertion = kind === "user" ? `@${value} ` : `(${value}) `;
    const next = before + insertion + after;
    setDraft(next);
    requestAnimationFrame(() => {
      const t = textareaRef.current;
      if (t) {
        const pos = (before + insertion).length;
        t.focus();
        t.setSelectionRange(pos, pos);
        setCaret(pos);
      }
    });
  };

  const handleSend = () => {
    const body = draft.trim();
    if (!body) return;

    // Resolve mentions
    const userMatches = Array.from(body.matchAll(/@([\p{L}0-9_.-]+)/gu));
    const mentionedIds: string[] = [];
    for (const m of userMatches) {
      const handle = m[1].toLowerCase();
      const u = users.find(
        (u) => u.full_name.toLowerCase().split(/\s+/).join(".") === handle
          || u.full_name.toLowerCase().split(/\s+/)[0] === handle
          || u.email.toLowerCase().split("@")[0] === handle,
      );
      if (u && !mentionedIds.includes(u.id)) mentionedIds.push(u.id);
    }

    const fieldMatches = Array.from(body.matchAll(/\(([^()]+)\)/g));
    const fieldRefs = Array.from(
      new Set(
        fieldMatches
          .map((m) => m[1].trim())
          .filter((f) => fieldNames.some((fn) => fn.toLowerCase() === f.toLowerCase())),
      ),
    );

    const msg: AlignmentMessage = {
      id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      author: currentAuthor,
      body,
      mentions: mentionedIds,
      fieldRefs,
      created_at: new Date().toISOString(),
    };

    const all = loadAll();
    const next = [...(all[componentId] || []), msg];
    all[componentId] = next;
    saveAll(all);
    setMessages(next);
    setDraft("");

    // Notify mentioned users
    for (const uid of mentionedIds) {
      pushAlignmentNotification({
        user_id: uid,
        component_id: componentId,
        message_id: msg.id,
        author: currentAuthor,
        excerpt: body.slice(0, 120),
      });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-1 pb-3 border-b border-border">
        <p className="text-xs text-muted-foreground">
          Discuss this component with your team. Type{" "}
          <code className="rounded bg-muted px-1 py-px text-[10px]">@name</code> to tag a
          teammate, or{" "}
          <code className="rounded bg-muted px-1 py-px text-[10px]">(Field Name)</code> to
          point at a parameter.
        </p>
      </div>

      {/* Thread */}
      <div ref={scrollRef} className="flex-1 min-h-[220px] max-h-[360px] overflow-y-auto py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-10 text-xs text-muted-foreground flex flex-col items-center gap-2">
            <MessageSquare className="h-5 w-5 opacity-50" />
            No alignment messages yet. Start the discussion below.
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className="rounded-lg border border-border bg-card px-3 py-2">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold text-foreground">{m.author}</span>
                {m.mentions.length > 0 && (
                  <Badge variant="outline" className="h-4 px-1.5 text-[9px] gap-0.5">
                    <AtSign className="h-2.5 w-2.5" />
                    {m.mentions.length}
                  </Badge>
                )}
                {m.fieldRefs.length > 0 && (
                  <Badge variant="outline" className="h-4 px-1.5 text-[9px] gap-0.5">
                    <Tag className="h-2.5 w-2.5" />
                    {m.fieldRefs.length}
                  </Badge>
                )}
              </div>
              <span className="text-[10px] text-muted-foreground">
                {new Date(m.created_at).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
            <div className="text-xs text-foreground whitespace-pre-wrap leading-relaxed">
              {renderBody(m.body, users, fieldNames)}
            </div>
          </div>
        ))}
      </div>

      {/* Composer */}
      <div className="relative pt-3 border-t border-border">
        {(userSuggestions.length > 0 || fieldSuggestions.length > 0) && (
          <div className="absolute bottom-full left-0 right-0 mb-1 max-h-44 overflow-y-auto rounded-lg border border-border bg-popover shadow-lg z-10">
            {activeToken?.kind === "user" &&
              userSuggestions.map((u) => (
                <button
                  key={u.id}
                  type="button"
                  onClick={() =>
                    insertSuggestion("user", u.full_name.split(/\s+/).join("."))
                  }
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent flex items-center justify-between"
                >
                  <span className="flex items-center gap-1.5">
                    <AtSign className="h-3 w-3 text-muted-foreground" />
                    <span className="font-medium">{u.full_name}</span>
                  </span>
                  <span className="text-[10px] text-muted-foreground">{u.email}</span>
                </button>
              ))}
            {activeToken?.kind === "field" &&
              fieldSuggestions.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => insertSuggestion("field", f)}
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent flex items-center gap-1.5"
                >
                  <Tag className="h-3 w-3 text-muted-foreground" />
                  <span className="font-mono">{f}</span>
                </button>
              ))}
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setCaret(e.target.selectionStart ?? e.target.value.length);
          }}
          onKeyUp={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart ?? 0)}
          onClick={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart ?? 0)}
          onKeyDown={handleKeyDown}
          placeholder={`Message the team about ${componentLabel || "this component"}…  Use @name or (Field)`}
          className="w-full min-h-[72px] resize-none rounded-md border border-input bg-background px-3 py-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-[10px] text-muted-foreground">⌘/Ctrl + Enter to send</span>
          <Button size="sm" className="h-7 text-xs gap-1.5" onClick={handleSend} disabled={!draft.trim()}>
            <Send className="h-3 w-3" />
            Post
          </Button>
        </div>
      </div>
    </div>
  );
};

export default TeamAlignmentPanel;