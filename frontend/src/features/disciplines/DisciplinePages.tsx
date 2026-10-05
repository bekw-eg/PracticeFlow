import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { showToast } from "../../lib/toast";
import { useLocaleFormatters } from "../../i18n/formatters";
import {
  downloadMaterial, MAX_MATERIAL_BYTES, useAvailableGroups, useDeleteMaterial, useDiscipline,
  useDisciplineGroups, useDisciplines, useMaterials, useSaveDiscipline, useSaveTopic, useTopic, useTopics, useUploadMaterial,
} from "./api";
import type { Discipline, TeachingMaterial, Topic } from "./types";

function CurriculumError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation("disciplines");
  const codes = {
    MATERIAL_INVALID: "invalidFile", MATERIAL_TYPE_UNSUPPORTED: "invalidType", MATERIAL_TOO_LARGE: "tooLarge",
    CURRICULUM_ARCHIVED: "archivedHint", IDEMPOTENCY_KEY_CONFLICT: "uploadConflict", MATERIAL_DELETE_PENDING: "deletePending",
  } as const;
  const code = isAxiosError<{ detail?: { code?: string } }>(error) ? error.response?.data?.detail?.code : undefined;
  const message = code && code in codes ? t(codes[code as keyof typeof codes]) : undefined;
  return <ErrorState compact error={error} message={message} onRetry={onRetry} />;
}

function offsetOf(params: URLSearchParams) {
  const offset = Number(params.get("offset"));
  return Number.isSafeInteger(offset) && offset > 0 ? offset : 0;
}

function DisciplineForm({ discipline, groupIds = [], onSaved, onCancel }: {
  discipline?: Discipline; groupIds?: string[]; onSaved: (discipline: Discipline) => void; onCancel?: () => void;
}) {
  const { t } = useTranslation(["disciplines", "common"]);
  const save = useSaveDiscipline(discipline?.id);
  const [selected, setSelected] = useState(groupIds);
  const [offset, setOffset] = useState(0);
  const groups = useAvailableGroups(offset);
  const submitting = useRef(false);
  return <form className="section-panel mb-5 space-y-4 p-5" onSubmit={event => {
    event.preventDefault();
    if (submitting.current || selected.length > 100) return;
    submitting.current = true;
    const data = new FormData(event.currentTarget);
    save.mutate({ name: String(data.get("name")).trim(), description: String(data.get("description")).trim() || null,
      academic_year: String(data.get("academic_year")).trim() || null, group_ids: selected }, {
      onSuccess: saved => { showToast(t("saved")); onSaved(saved); },
      onSettled: () => { submitting.current = false; },
    });
  }}>
    <fieldset disabled={save.isPending} className="space-y-4">
      <h2 className="font-bold">{t(discipline ? "edit" : "create")}</h2>
      <label className="block text-sm font-semibold">{t("name")}<input name="name" className="input mt-1 w-full" required maxLength={255} defaultValue={discipline?.name} /></label>
      <label className="block text-sm font-semibold">{t("description")}<textarea name="description" className="input mt-1 w-full" maxLength={5000} defaultValue={discipline?.description ?? ""} /></label>
      <label className="block text-sm font-semibold">{t("academicYear")}<input name="academic_year" className="input mt-1 w-full" maxLength={20} defaultValue={discipline?.academic_year ?? ""} /></label>
      <fieldset className="rounded-md border border-[var(--color-border)] p-3">
        <legend className="px-1 text-sm font-semibold">{t("chooseGroups")}</legend>
        {groups.isLoading && <LoadingState />}
        {groups.isError && <CurriculumError error={groups.error} onRetry={() => void groups.refetch()} />}
        {groups.data?.items.map(group => <label className="flex items-center gap-2 py-1 text-sm" key={group.id}>
          <input type="checkbox" checked={selected.includes(group.id)} disabled={!selected.includes(group.id) && selected.length >= 100}
            onChange={event => setSelected(previous => event.target.checked ? [...previous, group.id] : previous.filter(id => id !== group.id))} />
          {group.name}
        </label>)}
        {groups.data && <PaginationControls pagination={groups.data} onPageChange={setOffset} isFetching={groups.isFetching} label={t("groups")} />}
      </fieldset>
      {save.isError && <CurriculumError error={save.error} />}
      <div className="flex gap-2"><button className="btn btn-primary" disabled={save.isPending}>{t(discipline ? "common:save" : "common:create")}</button>
        {onCancel && <button type="button" className="btn btn-secondary" onClick={onCancel}>{t("common:cancel")}</button>}</div>
    </fieldset>
  </form>;
}

function DisciplineRow({ discipline }: { discipline: Discipline }) {
  const { t } = useTranslation("disciplines");
  const save = useSaveDiscipline(discipline.id);
  return <li className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] p-5">
    <div className="min-w-0"><Link className="font-bold text-[var(--color-brand-700)] break-words" to={`/disciplines/${discipline.id}`}>{discipline.name}</Link>
      {discipline.academic_year && <p className="mt-1 text-sm">{discipline.academic_year}</p>}
      {discipline.description && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-[var(--color-muted)]">{discipline.description}</p>}</div>
    <button className="btn btn-secondary" disabled={save.isPending} onClick={() => save.mutate({ is_archived: !discipline.is_archived },
      { onSuccess: () => showToast(t(discipline.is_archived ? "restored" : "archivedToast")) })}>{t(discipline.is_archived ? "restore" : "archive")}</button>
    {save.isError && <CurriculumError error={save.error} />}
  </li>;
}

export function DisciplinesPage() {
  const { t } = useTranslation("disciplines");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const archived = params.get("archived") === "true";
  const disciplines = useDisciplines(offsetOf(params), archived);
  return <div>
    <header className="mb-6"><h1 className="page-title">{t("title")}</h1><p className="page-description">{t("introduction")}</p></header>
    <DisciplineForm onSaved={row => navigate(`/disciplines/${row.id}`)} />
    <label className="mb-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={archived}
      onChange={event => setParams({ archived: String(event.target.checked) })} />{t("archived")}</label>
    {disciplines.isLoading && <LoadingState />}
    {disciplines.isError && <CurriculumError error={disciplines.error} onRetry={() => void disciplines.refetch()} />}
    {disciplines.data && <section className="section-panel overflow-hidden">
      {!disciplines.data.items.length && <EmptyState title={t("empty")} description={t("emptyHint")} />}
      <ul>{disciplines.data.items.map(row => <DisciplineRow key={row.id} discipline={row} />)}</ul>
      <div className="p-4"><PaginationControls pagination={disciplines.data} onPageChange={offset => setParams({ archived: String(archived), offset: String(offset) })} isFetching={disciplines.isFetching} label={t("title")} /></div>
    </section>}
  </div>;
}

function TopicForm({ disciplineId, topic, onSaved, onCancel }: {
  disciplineId: string; topic?: Topic; onSaved: (topic: Topic) => void; onCancel?: () => void;
}) {
  const { t } = useTranslation(["disciplines", "common"]);
  const save = useSaveTopic(disciplineId, topic?.id);
  const submitting = useRef(false);
  return <form className="section-panel mb-5 space-y-4 p-5" onSubmit={event => {
    event.preventDefault();
    if (submitting.current) return;
    const data = new FormData(event.currentTarget);
    const title = String(data.get("title")).trim();
    submitting.current = true;
    save.mutate({ title, description: String(data.get("description")).trim() || null,
      learning_goal: String(data.get("learning_goal")).trim() || null,
      ...(topic ? { position: Number(data.get("position")) } : {}),
    }, { onSuccess: row => { showToast(t("saved")); onSaved(row); }, onSettled: () => { submitting.current = false; } });
  }}>
    <fieldset disabled={save.isPending} className="space-y-4">
      <h2 className="font-bold">{t(topic ? "editTopic" : "createTopic")}</h2>
      <label className="block text-sm font-semibold">{t("topicTitle")}<input name="title" className="input mt-1 w-full" maxLength={255} required defaultValue={topic?.title} /></label>
      <label className="block text-sm font-semibold">{t("learningGoal")}<textarea name="learning_goal" className="input mt-1 w-full" maxLength={5000} defaultValue={topic?.learning_goal ?? ""} /></label>
      <label className="block text-sm font-semibold">{t("description")}<textarea name="description" className="input mt-1 w-full" maxLength={5000} defaultValue={topic?.description ?? ""} /></label>
      {topic && <label className="block text-sm font-semibold">{t("position")}<input name="position" type="number" min={0} max={1000000} required className="input mt-1 w-full" defaultValue={topic.position} /></label>}
      {save.isError && <CurriculumError error={save.error} />}
      <div className="flex gap-2"><button className="btn btn-primary" disabled={save.isPending}>{t(topic ? "common:save" : "common:create")}</button>
        {onCancel && <button type="button" className="btn btn-secondary" onClick={onCancel}>{t("common:cancel")}</button>}</div>
    </fieldset>
  </form>;
}

function TopicRow({ topic }: { topic: Topic }) {
  const { t } = useTranslation("disciplines");
  const save = useSaveTopic(topic.discipline_id, topic.id);
  return <li className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] p-5">
    <div className="min-w-0"><Link className="font-bold break-words text-[var(--color-brand-700)]" to={`/disciplines/${topic.discipline_id}/topics/${topic.id}`}>{topic.title}</Link>
      {topic.learning_goal && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-[var(--color-muted)]">{topic.learning_goal}</p>}</div>
    <button className="btn btn-secondary" disabled={save.isPending} onClick={() => save.mutate({ is_archived: !topic.is_archived },
      { onSuccess: () => showToast(t(topic.is_archived ? "restored" : "archivedToast")) })}>{t(topic.is_archived ? "restore" : "archive")}</button>
    {save.isError && <CurriculumError error={save.error} />}
  </li>;
}

export function DisciplinePage() {
  const { disciplineId = "" } = useParams();
  return <DisciplineDetail key={disciplineId} id={disciplineId} />;
}

function DisciplineDetail({ id }: { id: string }) {
  const { t } = useTranslation("disciplines");
  const navigate = useNavigate();
  const discipline = useDiscipline(id);
  const groups = useDisciplineGroups(id, !!discipline.data);
  const [params, setParams] = useSearchParams();
  const archived = params.get("archived") === "true";
  const topics = useTopics(id, offsetOf(params), archived, !!discipline.data);
  const [editing, setEditing] = useState(false);
  const save = useSaveDiscipline(id);
  if (discipline.isLoading) return <LoadingState />;
  if (!discipline.data) return <CurriculumError error={discipline.error} onRetry={() => void discipline.refetch()} />;
  const row = discipline.data;
  return <div>
    <Link className="text-sm font-semibold text-[var(--color-brand-700)]" to="/disciplines">{t("back")}</Link>
    <header className="my-5 flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h1 className="page-title break-words">{row.name}</h1>
      <p className="page-description whitespace-pre-wrap break-words">{row.description}</p>{row.academic_year && <p className="mt-1 text-sm">{row.academic_year}</p>}</div>
      <div className="flex gap-2">{!row.is_archived && <button className="btn btn-secondary" onClick={() => setEditing(!editing)}>{t("edit")}</button>}
        <button className="btn btn-secondary" disabled={save.isPending} onClick={() => save.mutate({ is_archived: !row.is_archived })}>{t(row.is_archived ? "restore" : "archive")}</button></div>
    </header>
    {save.isError && <CurriculumError error={save.error} />}
    {row.is_archived && <p className="section-panel mb-5 p-4 text-sm">{t("archivedHint")}</p>}
    {editing && !row.is_archived && groups.data && <DisciplineForm discipline={row} groupIds={groups.data.map(group => group.id)} onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />}
    <section className="section-panel mb-5 p-5"><h2 className="font-bold">{t("groups")}</h2>
      {groups.isLoading && <LoadingState />}{groups.isError && <CurriculumError error={groups.error} onRetry={() => void groups.refetch()} />}
      {groups.data && (groups.data.length ? <ul className="mt-3 flex flex-wrap gap-3">{groups.data.map(group => <li key={group.id}><Link className="btn btn-secondary" to={`/groups/${group.id}`}>{group.name}</Link></li>)}</ul> : <p className="mt-2 text-sm text-[var(--color-muted)]">{t("noGroups")}</p>)}
    </section>
    {!row.is_archived && <TopicForm disciplineId={id} onSaved={topic => navigate(`/disciplines/${id}/topics/${topic.id}`)} />}
    <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">{t("topics")}</h2>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={archived} onChange={event => setParams({ archived: String(event.target.checked) })} />{t("archived")}</label></div>
    {topics.isLoading && <LoadingState />}{topics.isError && <CurriculumError error={topics.error} onRetry={() => void topics.refetch()} />}
    {topics.data && <section className="section-panel overflow-hidden">
      {!topics.data.items.length && <EmptyState title={t("noTopics")} description={t("noTopicsHint")} />}
      <ul>{topics.data.items.map(topic => <TopicRow key={topic.id} topic={topic} />)}</ul>
      <div className="p-4"><PaginationControls pagination={topics.data} onPageChange={offset => setParams({ archived: String(archived), offset: String(offset) })} isFetching={topics.isFetching} label={t("topics")} /></div>
    </section>}
  </div>;
}

function MaterialUpload({ topicId }: { topicId: string }) {
  const { t } = useTranslation("disciplines");
  const upload = useUploadMaterial(topicId);
  const attempt = useRef<{ file: File; title: string; key: string } | null>(null);
  const busy = useRef(false);
  const [validation, setValidation] = useState<string | null>(null);
  return <form className="section-panel mb-5 p-5" onSubmit={event => {
    event.preventDefault();
    if (busy.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = (form.elements.namedItem("file") as HTMLInputElement).files?.[0];
    const title = String(data.get("title")).trim();
    if (!(file instanceof File) || !file.name) { setValidation(t("selectFile")); return; }
    if (!/\.(pdf|docx|pptx)$/i.test(file.name)) { setValidation(t("invalidType")); return; }
    if (file.size > MAX_MATERIAL_BYTES) { setValidation(t("tooLarge")); return; }
    setValidation(null);
    if (attempt.current?.file !== file || attempt.current.title !== title) {
      attempt.current = { file, title, key: crypto.randomUUID() };
    }
    busy.current = true;
    upload.mutate(attempt.current, {
      onSuccess: () => { form.reset(); attempt.current = null; showToast(t("uploaded")); },
      onSettled: () => { busy.current = false; },
    });
  }}>
    <fieldset disabled={upload.isPending} className="space-y-4">
      <h2 className="font-bold">{t("upload")}</h2>
      <p className="text-sm text-[var(--color-muted)]">{t("uploadHint")}</p>
      <label className="block text-sm font-semibold">{t("materialTitle")}<input className="input mt-1 w-full" name="title" maxLength={255} /></label>
      <label className="block text-sm font-semibold">{t("file")}<input className="input mt-1 w-full" type="file" name="file" required accept=".pdf,.docx,.pptx"
        onChange={() => { attempt.current = null; setValidation(null); upload.reset(); }} /></label>
      {validation && <p role="alert" className="text-sm text-[var(--color-danger-500)]">{validation}</p>}
      {upload.isError && <CurriculumError error={upload.error} />}
      <button className="btn btn-primary" disabled={upload.isPending}>{t(upload.isPending ? "uploading" : "upload")}</button>
    </fieldset>
  </form>;
}

function MaterialRow({ material, deleting, onDelete }: { material: TeachingMaterial; deleting: boolean; onDelete: () => void }) {
  const { t } = useTranslation("disciplines");
  const { formatDateTime, formatNumber } = useLocaleFormatters();
  const download = useMutation({ retry: false, mutationFn: () => downloadMaterial(material) });
  return <li className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] p-5">
    <div className="min-w-0"><h3 className="font-bold break-words">{material.title}</h3>
      <p className="mt-1 break-words text-sm text-[var(--color-muted)]">{material.original_filename} · {formatNumber(material.size_bytes)} B · {formatDateTime(material.created_at)}</p></div>
    <div className="flex gap-2"><button className="btn btn-secondary" disabled={download.isPending} onClick={() => download.mutate()}>{t(download.isPending ? "downloading" : "download")}</button>
      <button className="btn btn-secondary" disabled={deleting} onClick={onDelete}>{t("delete")}</button></div>
    {download.isError && <CurriculumError error={download.error} />}
  </li>;
}

export function TopicPage() {
  const { disciplineId = "", topicId = "" } = useParams();
  return <TopicDetail key={topicId + disciplineId} disciplineId={disciplineId} id={topicId} />;
}

function TopicDetail({ disciplineId, id }: { disciplineId: string; id: string }) {
  const { t } = useTranslation("disciplines");
  const topic = useTopic(id);
  const matches = !!topic.data && topic.data.discipline_id === disciplineId;
  const discipline = useDiscipline(disciplineId);
  const [params, setParams] = useSearchParams();
  const materials = useMaterials(id, offsetOf(params), matches && !!discipline.data);
  const remove = useDeleteMaterial(id);
  const save = useSaveTopic(disciplineId, id);
  const [editing, setEditing] = useState(false);
  if (topic.isLoading || discipline.isLoading) return <LoadingState />;
  if (!topic.data) return <CurriculumError error={topic.error} onRetry={() => void topic.refetch()} />;
  if (!discipline.data) return <CurriculumError error={discipline.error} onRetry={() => void discipline.refetch()} />;
  if (!matches) return <ErrorState message={t("wrongTopic")} />;
  const row = topic.data;
  const archived = row.is_archived || discipline.data.is_archived;
  return <div>
    <Link className="text-sm font-semibold text-[var(--color-brand-700)]" to={`/disciplines/${disciplineId}`}>{t("backToDiscipline")}</Link>
    <header className="my-5 flex flex-wrap items-start justify-between gap-3"><h1 className="page-title break-words">{row.title}</h1>
      <div className="flex gap-2">{!archived && <button className="btn btn-secondary" onClick={() => setEditing(!editing)}>{t("editTopic")}</button>}
        <button className="btn btn-secondary" disabled={save.isPending} onClick={() => save.mutate({ is_archived: !row.is_archived })}>{t(row.is_archived ? "restore" : "archive")}</button></div></header>
    {save.isError && <CurriculumError error={save.error} />}
    {archived && <p className="section-panel mb-5 p-4 text-sm">{t("archivedHint")}</p>}
    {editing && !archived && <TopicForm disciplineId={disciplineId} topic={row} onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />}
    <section className="section-panel mb-5 space-y-4 p-5">
      <div><h2 className="font-bold">{t("learningGoal")}</h2><p className="mt-2 whitespace-pre-wrap break-words text-sm">{row.learning_goal || "—"}</p></div>
      <div><h2 className="font-bold">{t("description")}</h2><p className="mt-2 whitespace-pre-wrap break-words text-sm">{row.description || "—"}</p></div>
    </section>
    {!archived && <MaterialUpload topicId={id} />}
    <h2 className="mb-4 font-bold">{t("materials")}</h2>
    {remove.isError && <div className="mb-4"><CurriculumError error={remove.error} />
      <button className="btn btn-secondary mt-2" disabled={remove.isPending} onClick={() => { if (remove.variables) remove.mutate(remove.variables); }}>{t("retryDelete")}</button></div>}
    {materials.isLoading && <LoadingState />}{materials.isError && <CurriculumError error={materials.error} onRetry={() => void materials.refetch()} />}
    {materials.data && <section className="section-panel overflow-hidden">
      {!materials.data.items.length && <EmptyState title={t("noMaterials")} description={t("noMaterialsHint")} />}
      <ul>{materials.data.items.map(material => <MaterialRow key={material.id} material={material} deleting={remove.isPending}
        onDelete={() => { if (window.confirm(t("confirmDelete"))) remove.mutate(material.id, { onSuccess: () => showToast(t("deleted")) }); }} />)}</ul>
      <div className="p-4"><PaginationControls pagination={materials.data} onPageChange={offset => setParams({ offset: String(offset) })} isFetching={materials.isFetching} label={t("materials")} /></div>
    </section>}
  </div>;
}
