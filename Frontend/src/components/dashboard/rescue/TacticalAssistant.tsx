import { useState } from 'react';
import { Navigation, RefreshCw, Send } from 'lucide-react';
import type { ChatMessage, VerifiedRoute } from '@/types/domain';
import { api } from '@/services/api';
import type { SessionEvent } from './useCommandCentreData';
import { DataBadge, SectionCard } from './rescueShared';

export interface RouteRecord {
  id: string;
  at: string;
  query: string;
  text: string;
  route: VerifiedRoute;
}

const QUICK_CHIPS = [
  '/shelter current loc - ',
  '/safe-route to Hospital from - ',
  '/flood-status at - ',
  '/convoy-clearance from - ',
];

const CLEARANCE_STYLE: Record<VerifiedRoute['clearanceStatus'], string> = {
  VERIFIED_CLEAR: 'border-emerald-700 bg-emerald-50 text-emerald-800',
  CAUTION_RESTRICTED: 'border-amber-600 bg-amber-50 text-amber-900',
  IMPASSABLE_FLOOD: 'border-red-700 bg-red-50 text-red-800',
};

function initialMessages(regionName: string): ChatMessage[] {
  return [
    {
      id: 'tactical-welcome',
      sender: 'system',
      senderName: '3P Tactical Assistant',
      text: `Tactical assistant ready for ${regionName}. I answer from live facility data for this region and AI-assisted routing. Routes are advisory text guidance — verify conditions on the ground before any movement.`,
      timestamp: 'now',
    },
  ];
}

function stamp(): string {
  return `${new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} IST`;
}

export function TacticalAssistant({
  regionKey,
  regionName,
  onRoute,
  logSessionEvent,
}: {
  regionKey: string;
  regionName: string;
  onRoute: (record: RouteRecord) => void;
  logSessionEvent: (event: Omit<SessionEvent, 'id' | 'at'>) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => initialMessages(regionName));
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [failedQuery, setFailedQuery] = useState<string | null>(null);

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend ?? inputText).trim();
    if (!query || isTyping) return;

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'officer',
      senderName: 'Command Officer',
      text: query,
      timestamp: stamp(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setFailedQuery(null);
    setIsTyping(true);

    try {
      const aiData = await api.sendDispatchChat(query, regionKey);
      const systemMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: 'system',
        senderName: '3P Tactical Assistant',
        text: aiData.text,
        timestamp: stamp(),
        verifiedRoute: aiData.verifiedRoute,
      };
      setMessages((prev) => [...prev, systemMsg]);
      if (aiData.verifiedRoute) {
        onRoute({
          id: systemMsg.id,
          at: new Date().toISOString(),
          query,
          text: aiData.text,
          route: aiData.verifiedRoute,
        });
        logSessionEvent({
          title: `Route advisory: ${aiData.verifiedRoute.origin} → ${aiData.verifiedRoute.destination}`,
          detail: `Clearance ${aiData.verifiedRoute.clearanceStatus.replace(/_/g, ' ')}. AI-assisted; re-verify before movement.`,
          tone: 'slate',
        });
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'The dispatch service could not be reached.';
      setFailedQuery(query);
      const errorMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: 'system',
        senderName: 'System Error',
        text: `Dispatch request failed: ${reason} Do not use an unverified route; retry the request or fall back to manual radio procedure.`,
        timestamp: stamp(),
      };
      setMessages((prev) => [...prev, errorMsg]);
      logSessionEvent({
        title: 'Tactical query failed',
        detail: reason,
        tone: 'red',
      });
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <SectionCard
      title="AI Tactical Assistant"
      subtitle="Facility lookup and advisory routing. Outputs also feed Route Intelligence."
      badge={<DataBadge provenance="estimated" title="AI-assisted text over live facility data. Advisory only — not surveyed clearance." />}
      className="h-full"
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-60 flex-1 space-y-3 overflow-y-auto bg-slate-50/60 p-3 lg:max-h-[460px]" aria-live="polite">
          {messages.map((msg) => {
            const isOfficer = msg.sender === 'officer';
            return (
              <div key={msg.id} className={`flex flex-col ${isOfficer ? 'items-end' : 'items-start'}`}>
                <div className="mb-1 flex items-center gap-2 px-1">
                  <span className="font-mono text-[11px] font-bold text-slate-700">{msg.senderName}</span>
                  <span className="font-mono text-[10px] text-slate-400">{msg.timestamp}</span>
                </div>
                <div
                  className={`max-w-full rounded-lg p-3 text-xs leading-relaxed sm:max-w-xl ${
                    isOfficer
                      ? 'rounded-tr-none bg-blue-700 text-white shadow-sm'
                      : 'rounded-tl-none border border-slate-200 bg-white text-slate-800 shadow-xs'
                  }`}
                >
                  <p>{msg.text}</p>
                  {!isOfficer && msg.senderName !== 'System Error' && (
                    <p className="mt-1.5 text-[10px] italic text-slate-400">
                      AI-assisted advisory — verify on the ground before movement.
                    </p>
                  )}
                  {msg.verifiedRoute && (
                    <div className="mt-2.5 space-y-2 border border-slate-200 bg-slate-50 p-2.5 text-slate-800">
                      <div className="flex items-center justify-between gap-2 border-b border-slate-200 pb-1.5">
                        <span className="flex items-center gap-1.5 text-xs font-bold">
                          <Navigation size={13} className="text-emerald-700" /> Routing Advisory
                        </span>
                        <span className={`border px-1.5 py-0.5 font-mono text-[10px] font-bold ${CLEARANCE_STYLE[msg.verifiedRoute.clearanceStatus]}`}>
                          {msg.verifiedRoute.clearanceStatus.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-[11px]">
                        <div>
                          <span className="text-slate-500">Max water depth</span>
                          <div className="mt-0.5 font-mono font-bold text-slate-900">{msg.verifiedRoute.waterDepth}</div>
                        </div>
                        <div>
                          <span className="text-slate-500">Validity</span>
                          <div className="mt-0.5 font-mono font-semibold text-blue-800">{msg.verifiedRoute.validityWindow}</div>
                        </div>
                      </div>
                      <div className="text-[11px]">
                        <span className="text-slate-500">Recommended path</span>
                        <div className="mt-0.5 font-semibold leading-snug text-emerald-800">{msg.verifiedRoute.recommendedPath}</div>
                      </div>
                      <div className="text-[11px]">
                        <span className="text-slate-500">Waypoints</span>
                        <ul className="mt-1 list-inside list-disc space-y-0.5 text-slate-700">
                          {msg.verifiedRoute.waypoints.map((wp, idx) => (
                            <li key={idx}>{wp}</li>
                          ))}
                        </ul>
                      </div>
                      <p className="border-t border-slate-200 pt-1.5 text-[10px] text-slate-500">
                        Source note: {msg.verifiedRoute.sensorVerification}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {isTyping && (
            <div className="flex max-w-xs items-center gap-2 rounded-lg border border-slate-200 bg-white p-2.5 text-xs italic text-slate-600 shadow-xs">
              <RefreshCw size={13} className="animate-spin text-blue-700" />
              <span>Analyzing tactical routing…</span>
            </div>
          )}
          {failedQuery && !isTyping && (
            <button
              type="button"
              onClick={() => handleSendMessage(failedQuery)}
              className="inline-flex items-center gap-1.5 border border-amber-400 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
            >
              <RefreshCw size={13} /> Retry last query
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 overflow-x-auto border-t border-slate-200 bg-white px-3 py-2">
          <span className="shrink-0 font-mono text-[10px] uppercase text-slate-500">Commands:</span>
          {QUICK_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => setInputText(chip)}
              className="shrink-0 whitespace-nowrap border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
            >
              {chip.replace(' - ', '')}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 border-t border-slate-200 bg-white p-2.5">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleSendMessage();
            }}
            placeholder="Ask for shelters, hospitals, flood status, safe routes…"
            aria-label="Tactical assistant query"
            className="flex-1 border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#18365b]"
          />
          <button
            type="button"
            onClick={() => void handleSendMessage()}
            disabled={!inputText.trim() || isTyping}
            className="inline-flex items-center gap-1.5 bg-blue-700 px-3.5 py-2 text-xs font-bold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            <span>Ask</span>
            <Send size={12} />
          </button>
        </div>
      </div>
    </SectionCard>
  );
}
