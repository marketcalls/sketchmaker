import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getErrorMessage } from '@/utils/errors';
import { facelessApi, type FacelessSeries } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { CastPicker } from './CastPicker';
import { ErrorNote, FieldLabel } from './shared';

export function SeriesDialog({
  open,
  onOpenChange,
  series,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  series: FacelessSeries | null;
  onSaved?: (s: FacelessSeries) => void;
}) {
  const { templates, styles, characters, voices, upsertSeries } = useFacelessStore();
  const [title, setTitle] = useState('');
  const [logline, setLogline] = useState('');
  const [world, setWorld] = useState('');
  const [tone, setTone] = useState('');
  const [rules, setRules] = useState('');
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [style, setStyle] = useState<string | null>(null);
  const [cast, setCast] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle(series?.title ?? '');
    setLogline(series?.logline ?? '');
    setWorld(series?.world_notes ?? '');
    setTone(series?.tone ?? '');
    setRules((series?.rules ?? []).join('\n'));
    setTemplateId(series?.template_id ?? null);
    setStyle(series?.style ?? null);
    setCast(series?.cast_ids ?? []);
    setError(null);
  }, [open, series]);

  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        title: title.trim(),
        logline: logline.trim() || null,
        world_notes: world.trim() || null,
        tone: tone.trim() || null,
        rules: rules.split('\n').map((r) => r.trim()).filter(Boolean),
        template_id: templateId,
        style,
        cast_ids: cast,
      };
      const saved = series ? await facelessApi.updateSeries(series.id, body) : await facelessApi.createSeries(body);
      upsertSeries(saved);
      onSaved?.(saved);
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the series'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{series ? 'Edit series' : 'New series'}</DialogTitle>
          <DialogDescription>
            A series keeps the cast, world and episode memory, so each episode varies the story instead of repeating it.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <FieldLabel htmlFor="fs-title">Title</FieldLabel>
            <Input id="fs-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="Milo and the Night Market" />
          </div>
          <div>
            <FieldLabel htmlFor="fs-logline">Logline</FieldLabel>
            <Textarea id="fs-logline" rows={2} value={logline} onChange={(e) => setLogline(e.target.value)} maxLength={2000} />
          </div>
          <div>
            <FieldLabel htmlFor="fs-world" hint="places, history, running jokes">World notes</FieldLabel>
            <Textarea id="fs-world" rows={3} value={world} onChange={(e) => setWorld(e.target.value)} maxLength={8000} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="fs-tone">Tone</FieldLabel>
              <Input id="fs-tone" value={tone} onChange={(e) => setTone(e.target.value)} maxLength={200} placeholder="Warm, funny, a little bittersweet" />
            </div>
            <div>
              <FieldLabel htmlFor="fs-style">Visual style</FieldLabel>
              <Select value={style ?? '__none'} onValueChange={(v) => setStyle(v === '__none' ? null : v)}>
                <SelectTrigger id="fs-style">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">Per episode</SelectItem>
                  {styles.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <FieldLabel htmlFor="fs-template" hint="optional">Default template</FieldLabel>
            <Select value={templateId ?? '__none'} onValueChange={(v) => setTemplateId(v === '__none' ? null : v)}>
              <SelectTrigger id="fs-template">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">Any template</SelectItem>
                {templates.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <FieldLabel htmlFor="fs-rules" hint="one per line">Continuity rules</FieldLabel>
            <Textarea id="fs-rules" rows={3} value={rules} onChange={(e) => setRules(e.target.value)} placeholder="Milo never wins by cheating" />
          </div>
          <div>
            <FieldLabel>Recurring cast</FieldLabel>
            <CastPicker characters={characters} voices={voices} value={cast} onChange={setCast} />
          </div>
          <ErrorNote>{error}</ErrorNote>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={busy || !title.trim()}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {series ? 'Save series' : 'Create series'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
