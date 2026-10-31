import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  ClipboardList,
  LoaderCircle,
  MapPin,
  MessageSquareText,
  Paperclip,
  RotateCcw,
  Search,
  Send,
  X,
} from 'lucide-react';
import {
  tasksApi,
  type BackendTask,
  type OperationalTaskStatus,
  type ReportPhoto,
} from '@/services/operationalApi';
import type { TaskPriority } from '@/utils/taskReview';

type TaskStatus = OperationalTaskStatus;

const MAX_PHOTOS = 5;
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;

type SelectedPhoto = ReportPhoto;

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(new Error('Unable to read the selected file.'));
    reader.readAsDataURL(file);
  });
}

interface FieldTask {
  backendId: string;
  displayId: string;
  title: string;
  location: string;
  department: string;
  assignedBy: string;
  due: string;
  priority: TaskPriority;
  status: TaskStatus;
  progress: number;
  description: string;
  instructions: string;
  reports: BackendTask['reports'];
}

const priorityClass: Record<TaskPriority, string> = {
  Critical: 'border-red-200 bg-red-50 text-red-700',
  High: 'border-amber-200 bg-amber-50 text-amber-800',
  Medium: 'border-blue-200 bg-blue-50 text-blue-800',
  Low: 'border-slate-200 bg-slate-100 text-slate-600',
};

const statusClass: Record<TaskStatus, string> = {
  Assigned: 'bg-slate-100 text-slate-700',
  'In Progress': 'bg-blue-50 text-blue-800',
  Submitted: 'bg-emerald-50 text-emerald-800',
};

function formatDue(value: string | null): string {
  if (!value) return 'No deadline set';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'No deadline set';
  return parsed.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function mapBackendTask(task: BackendTask): FieldTask {
  return {
    backendId: task.id,
    displayId: `F-${task.id.slice(0, 6).toUpperCase()}`,
    title: task.title,
    location: task.location,
    department: task.department,
    assignedBy: task.createdByName || 'Operations Planning Cell',
    due: formatDue(task.deadline),
    priority: task.priority,
    status: task.status,
    progress: task.progress,
    description: task.instructions || task.title,
    instructions: task.instructions || '',
    reports: task.reports ?? [],
  };
}

export default function FieldOperationsPage() {
  const [tasks, setTasks] = useState<FieldTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [filter, setFilter] = useState<'All' | TaskStatus>('All');
  const [query, setQuery] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [reportText, setReportText] = useState('');
  const [peopleAssisted, setPeopleAssisted] = useState('');
  const [locationNote, setLocationNote] = useState('');
  const [photos, setPhotos] = useState<SelectedPhoto[]>([]);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [readingPhotos, setReadingPhotos] = useState(false);
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    tasksApi
      .list()
      .then((backendTasks) => {
        if (cancelled) return;
        const mapped = backendTasks.map(mapBackendTask);
        setTasks(mapped);
        setSelectedTaskId((current) => {
          if (current && mapped.some((task) => task.backendId === current)) return current;
          return mapped[0]?.backendId ?? null;
        });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setTasks([]);
          setLoadError(error instanceof Error ? error.message : 'Unable to load assigned tasks.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const selectedTask = tasks.find((task) => task.backendId === selectedTaskId) ?? tasks[0] ?? null;

  const visibleTasks = useMemo(() => tasks.filter((task) => {
    const matchesFilter = filter === 'All' || task.status === filter;
    const searchText = `${task.title} ${task.location} ${task.displayId}`.toLowerCase();
    return matchesFilter && searchText.includes(query.toLowerCase());
  }), [tasks, filter, query]);

  const stats = {
    assigned: tasks.filter((task) => task.status === 'Assigned').length,
    progress: tasks.filter((task) => task.status === 'In Progress').length,
    submitted: tasks.filter((task) => task.status === 'Submitted').length,
    urgent: tasks.filter((task) => task.priority === 'Critical' && task.status !== 'Submitted').length,
  };

  const updateStatus = async (status: TaskStatus) => {
    if (!selectedTask || saving) return;
    setSaving(true);
    try {
      // Start / Update moves the bar to 50%; Mark Submitted completes it at 100%.
      const progress = status === 'In Progress' ? 50 : status === 'Submitted' ? 100 : undefined;
      const updated = await tasksApi.update(selectedTask.backendId, { status, progress });
      setTasks((current) => current.map((task) =>
        task.backendId === selectedTask.backendId ? mapBackendTask(updated) : task,
      ));
      setNotice(status === 'Submitted'
        ? 'Field report marked as submitted and confirmed by the backend. The Operations Planner has been notified.'
        : `Task started — progress set to 50%.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update the task status.');
    } finally {
      setSaving(false);
    }
  };

  const handlePhotoSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (files.length === 0) return;
    setPhotoError(null);
    const accepted = files.filter((file) => file.type.startsWith('image/'));
    if (accepted.length < files.length) {
      setPhotoError('Only image files can be attached as photo evidence.');
    }
    const oversized = accepted.filter((file) => file.size > MAX_PHOTO_BYTES);
    if (oversized.length > 0) {
      setPhotoError(`Each photo must be ${MAX_PHOTO_BYTES / (1024 * 1024)} MB or smaller.`);
      return;
    }
    if (photos.length + accepted.length > MAX_PHOTOS) {
      setPhotoError(`You can attach up to ${MAX_PHOTOS} photos per report.`);
      return;
    }
    setReadingPhotos(true);
    try {
      const loaded = await Promise.all(accepted.map(async (file) => ({
        filename: file.name,
        mimeType: file.type || 'image/jpeg',
        size: file.size,
        dataUrl: await readFileAsDataUrl(file),
      })));
      setPhotos((current) => [...current, ...loaded].slice(0, MAX_PHOTOS));
    } catch (error) {
      setPhotoError(error instanceof Error ? error.message : 'Unable to read the selected photos.');
    } finally {
      setReadingPhotos(false);
    }
  };

  const removePhoto = (index: number) => {
    setPhotos((current) => current.filter((_, position) => position !== index));
  };

  const submitReport = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedTask || saving) return;
    if (!reportText.trim()) {
      setNotice('Please enter field observations before submitting the report.');
      return;
    }
    const assisted = peopleAssisted.trim() === '' ? null : Number(peopleAssisted);
    if (assisted !== null && (!Number.isInteger(assisted) || assisted < 0)) {
      setNotice('People assisted must be a whole number of 0 or more.');
      return;
    }
    setSaving(true);
    try {
      const updated = await tasksApi.update(selectedTask.backendId, {
        report: {
          text: reportText.trim(),
          peopleAssisted: assisted,
          locationNote: locationNote.trim() || null,
          photos,
        },
      });
      setTasks((current) => current.map((task) =>
        task.backendId === selectedTask.backendId ? mapBackendTask(updated) : task,
      ));
      setNotice('Field report submitted and confirmed by the backend. The Operations Planner has been notified.');
      setReportText('');
      setPeopleAssisted('');
      setLocationNote('');
      setPhotos([]);
      setPhotoError(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to submit the field report.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="">
      <div className=" space-y-6">
        {notice && (
          <div role="status" className="flex items-start justify-between gap-3 border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
            <span>{notice}</span>
            <button type="button" onClick={() => setNotice('')} aria-label="Dismiss message"><X size={16} /></button>
          </div>
        )}

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Assigned Tasks" value={stats.assigned + stats.progress} hint="Tasks requiring action" icon={ClipboardList} />
          <StatCard label="In Progress" value={stats.progress} hint="Active field work" icon={Clock3} />
          <StatCard label="Reports Submitted" value={stats.submitted} hint="Sent for review" icon={CheckCircle2} />
          <StatCard label="Urgent Attention" value={stats.urgent} hint="Priority response required" icon={AlertTriangle} />
        </section>

        {loading ? (
          <p role="status" className="flex items-center gap-2 border border-slate-200 bg-white px-4 py-10 text-sm text-slate-600">
            <LoaderCircle size={16} className="animate-spin" /> Loading your assigned tasks…
          </p>
        ) : loadError ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-2 border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <span>{loadError}</span>
            <button type="button" onClick={() => setRetryCount((value) => value + 1)} className="inline-flex items-center gap-1.5 font-semibold underline underline-offset-2">
              <RotateCcw size={13} /> Retry
            </button>
          </div>
        ) : tasks.length === 0 ? (
          <div className="border border-dashed border-slate-300 bg-white px-4 py-10 text-center">
            <ClipboardList size={22} className="mx-auto text-slate-400" />
            <p className="mt-2 text-sm font-medium text-slate-700">No tasks assigned yet</p>
            <p className="mt-1 text-xs text-slate-500">Tasks assigned by the Operations Planner (Role 2) will appear here.</p>
          </div>
        ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <section className="min-w-0 border border-slate-200 bg-white">
            <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-bold text-[#18365b]">My Assigned Tasks</h2>
                <p className="mt-1 text-xs text-slate-500">Select a task to update its field status.</p>
              </div>
              <div className="relative">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search tasks..."
                  className="w-full border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-[#18365b] sm:w-48" />
              </div>
            </div>

            <div className="flex flex-wrap gap-2 border-b border-slate-200 px-4 py-3">
              {(['All', 'Assigned', 'In Progress', 'Submitted'] as const).map((item) => (
                <button key={item} type="button" onClick={() => setFilter(item)}
                  className={`border px-3 py-1.5 text-xs font-medium ${filter === item ? 'border-[#18365b] bg-[#18365b] text-white' : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'}`}>
                  {item}
                </button>
              ))}
            </div>

            <div className="divide-y divide-slate-200">
              {visibleTasks.map((task) => (
                <button type="button" key={task.backendId} onClick={() => { setSelectedTaskId(task.backendId); setNotice(''); }}
                  className={`block w-full p-4 text-left transition-colors hover:bg-slate-50 ${selectedTaskId === task.backendId || (!selectedTaskId && selectedTask?.backendId === task.backendId) ? 'border-l-4 border-l-[#d88b2b] bg-blue-50/50' : 'border-l-4 border-l-transparent'}`}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{task.displayId} · {task.department}</p>
                      <h3 className="mt-1 text-sm font-semibold text-slate-900">{task.title}</h3>
                    </div>
                    <span className={`border px-2 py-1 text-[10px] font-semibold ${priorityClass[task.priority]}`}>{task.priority}</span>
                  </div>
                  <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500"><MapPin size={13} />{task.location}</p>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <span className={`px-2 py-1 text-[10px] font-semibold ${statusClass[task.status]}`}>{task.status}</span>
                    <span className="text-[10px] text-slate-500">Due: {task.due}</span>
                  </div>
                  <div className="mt-3 h-1.5 bg-slate-100">
                    <div className="h-1.5 bg-[#18365b]" style={{ width: `${task.progress}%` }} />
                  </div>
                  <p className="mt-1 text-right text-[10px] text-slate-500">{task.progress}% complete</p>
                </button>
              ))}
              {visibleTasks.length === 0 && <p className="p-6 text-sm text-slate-500">No tasks match your search.</p>}
            </div>
          </section>

          {selectedTask && (
          <div className="space-y-6">
            <section className="border border-slate-200 bg-white">
              <div className="border-b border-slate-200 p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Selected task · {selectedTask.displayId}</p>
                <h2 className="mt-1 text-lg font-bold text-[#18365b]">{selectedTask.title}</h2>
                <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500"><MapPin size={13} />{selectedTask.location}</p>
              </div>
              <div className="space-y-4 p-4">
                <p className="text-sm leading-6 text-slate-600">{selectedTask.description}</p>
                <div className="grid grid-cols-2 gap-3">
                  <InfoCell label="Assigned by" value={selectedTask.assignedBy} />
                  <InfoCell label="Due time" value={selectedTask.due} />
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-700">Task progress</span>
                    <span className="font-bold text-[#18365b]">{selectedTask.progress}%</span>
                  </div>
                  <div className="h-2 bg-slate-100"><div className="h-2 bg-[#18365b]" style={{ width: `${selectedTask.progress}%` }} /></div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => updateStatus('In Progress')}
                    disabled={saving || selectedTask.status !== 'Assigned'}
                    title={selectedTask.status === 'Assigned' ? 'Start the task and set progress to 50%' : 'Task already started'}
                    className="inline-flex items-center gap-2 border border-[#18365b] px-3 py-2 text-xs font-semibold text-[#18365b] hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50">
                    <ArrowUpRight size={14} /> {saving ? 'Saving…' : 'Start / Update'}
                  </button>
                  <button type="button" onClick={() => updateStatus('Submitted')}
                    disabled={saving || selectedTask.status === 'Submitted'}
                    title={selectedTask.status === 'Submitted' ? 'Task already submitted' : 'Mark the task submitted at 100%'}
                    className="inline-flex items-center gap-2 bg-[#18365b] px-3 py-2 text-xs font-semibold text-white hover:bg-[#102744] disabled:cursor-not-allowed disabled:opacity-50">
                    <CheckCircle2 size={14} /> Mark Submitted
                  </button>
                </div>
              </div>
            </section>

            <section className="border border-slate-200 bg-white">
              <div className="border-b border-slate-200 p-4">
                <h2 className="font-bold text-[#18365b]">Field Situation Report</h2>
                <p className="mt-1 text-xs text-slate-500">Record observations for the selected task.</p>
              </div>
              <form onSubmit={submitReport} className="space-y-4 p-4">
                <label className="block text-xs font-semibold text-slate-700">
                  Field observations <span className="text-red-600">*</span>
                  <textarea value={reportText} onChange={(e) => setReportText(e.target.value)} rows={3}
                    placeholder="Describe ground conditions, damage, access and risks..."
                    className="mt-1.5 block w-full resize-y border border-slate-300 px-3 py-2 text-sm font-normal outline-none focus:border-[#18365b]" />
                </label>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label className="block text-xs font-semibold text-slate-700">
                    People assisted
                    <input type="number" min="0" value={peopleAssisted} onChange={(e) => setPeopleAssisted(e.target.value)}
                      placeholder="e.g. 25" className="mt-1.5 block w-full border border-slate-300 px-3 py-2 text-sm font-normal outline-none focus:border-[#18365b]" />
                  </label>
                  <label className="block text-xs font-semibold text-slate-700">
                    Location / landmark
                    <input value={locationNote} onChange={(e) => setLocationNote(e.target.value)}
                      placeholder="Ward, road or landmark" className="mt-1.5 block w-full border border-slate-300 px-3 py-2 text-sm font-normal outline-none focus:border-[#18365b]" />
                  </label>
                </div>
<div className="border border-dashed border-slate-300 bg-slate-50 px-3 py-3">
  <div className="flex flex-wrap items-center justify-between gap-2">
    <div>
      <p className="flex items-center gap-2 text-xs font-semibold text-slate-700">
        <Paperclip size={14} /> Photo evidence (optional)
      </p>
      <p className="mt-1 text-[10px] text-slate-500">
        Up to {MAX_PHOTOS} images · {MAX_PHOTO_BYTES / (1024 * 1024)} MB each
      </p>
    </div>

    <label
      htmlFor="field-report-photos"
      className={`inline-flex cursor-pointer items-center gap-1.5 border border-[#18365b] bg-white px-3 py-1.5 text-xs font-semibold text-[#18365b] hover:bg-blue-50 ${
        saving || readingPhotos ? 'pointer-events-none opacity-50' : ''
      }`}
    >
      {readingPhotos ? 'Reading…' : 'Choose photos'}
    </label>

    <input
      id="field-report-photos"
      type="file"
      accept="image/*"
      multiple
      onChange={handlePhotoSelect}
      disabled={saving || readingPhotos}
      className="hidden"
      aria-label="Attach photo evidence"
    />
  </div>

  {photoError && (
    <p role="alert" className="mt-2 text-xs text-red-700">
      {photoError}
    </p>
  )}

  {photos.length > 0 && (
    <ul className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-5">
      {photos.map((photo, index) => (
        <li
          key={`${photo.filename}-${index}`}
          className="relative border border-slate-300 bg-white"
        >
          <img
            src={photo.dataUrl}
            alt={photo.filename}
            className="h-16 w-full object-cover"
          />
          <button
            type="button"
            onClick={() => removePhoto(index)}
            aria-label={`Remove ${photo.filename}`}
            className="absolute right-0.5 top-0.5 bg-slate-900/70 p-0.5 text-white hover:bg-slate-900"
          >
            <X size={12} />
          </button>
        </li>
      ))}
    </ul>
  )}
</div>
                <button type="submit" disabled={saving} className="inline-flex w-full items-center justify-center gap-2 bg-[#18365b] px-4 py-3 text-sm font-semibold text-white hover:bg-[#102744] disabled:cursor-not-allowed disabled:opacity-50">
                  <Send size={15} /> {saving ? 'Submitting…' : 'Submit Field Report'}
                </button>
              </form>
            </section>

            {selectedTask.reports.length > 0 && (
              <section className="border border-slate-200 bg-white">
                <div className="border-b border-slate-200 p-4">
                  <h2 className="font-bold text-[#18365b]">Submitted reports ({selectedTask.reports.length})</h2>
                </div>
                <ul className="divide-y divide-slate-200">
                  {selectedTask.reports.map((report, index) => (
                    <li key={`${report.at}-${index}`} className="p-4 text-xs leading-5 text-slate-700">
                      <p>{report.text}</p>
                      <p className="mt-1 text-[10px] text-slate-500">
                        {formatDateTime(report.at)} · by {report.byName}
                        {report.peopleAssisted !== null && report.peopleAssisted !== undefined ? ` · assisted ${report.peopleAssisted}` : ''}
                        {report.locationNote ? ` · ${report.locationNote}` : ''}
                      </p>
                      {(report.photos ?? []).length > 0 && (
                        <ul className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4">
                          {(report.photos ?? []).map((photo, photoIndex) => (
                            <li key={`${photo.filename}-${photoIndex}`} className="border border-slate-200">
                              <a href={photo.dataUrl} target="_blank" rel="noreferrer" title={photo.filename}>
                                <img src={photo.dataUrl} alt={photo.filename} className="h-16 w-full object-cover" loading="lazy" />
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="border border-amber-200 bg-amber-50 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-700" />
                <div>
                  <h2 className="text-sm font-bold text-amber-900">Safety / resource escalation</h2>
                  <p className="mt-1 text-xs leading-5 text-amber-800">Report blocked routes, urgent medical needs, unsafe structures or resource shortages to the control room promptly.</p>
                  <button type="button" onClick={() => { setReportText((current) => current || 'ESCALATION: '); setNotice('Describe the escalation in the report box above and submit it.'); }}
                    className="mt-3 inline-flex items-center gap-2 border border-amber-300 bg-white px-3 py-2 text-xs font-semibold text-amber-900 hover:bg-amber-100">
                    <MessageSquareText size={14} /> Raise an escalation
                  </button>
                </div>
              </div>
            </section>
          </div>
          )}
        </div>
        )}

      </div>
    </main>
  );
}

function StatCard({ label, value, hint, icon: Icon }: { label: string; value: number; hint: string; icon: React.ElementType }) {
  return (
    <div className="border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-bold tracking-tight text-[#18365b]">{value}</p>
          <p className="mt-1 text-[10px] text-slate-500">{hint}</p>
        </div>
        <div className="border border-slate-200 bg-slate-50 p-2 text-[#18365b]"><Icon size={18} /></div>
      </div>
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-slate-200 bg-slate-50 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xs font-medium text-slate-800">{value}</p>
    </div>
  );
}
