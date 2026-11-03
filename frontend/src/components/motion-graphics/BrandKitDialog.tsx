import { useEffect, useState } from 'react';
import { ImagePlus, Loader2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { getErrorMessage } from '@/utils/errors';
import { motionGraphicsApi, type BrandKit, type Intensity } from '@/api/motionGraphics';
import { useMotionGraphicsStore } from '@/stores/motionGraphicsStore';
import { ErrorNote, FieldLabel, PillGroup } from './shared';

const NONE = '__none__';
const SWATCH_KEYS: { key: keyof BrandKit['palette']; label: string }[] = [
  { key: 'primary', label: 'Primary (accent)' },
  { key: 'secondary', label: 'Secondary' },
  { key: 'background', label: 'Background' },
  { key: 'text', label: 'Text' },
];
const HEX = /^#[0-9a-fA-F]{6}$/;

// The account brand kit: logo, palette tokens, bundled fonts and motion
// intensity. New projects copy it when auto-apply is on; a project re-applies
// it from the studio's Brand panel.
export function BrandKitDialog({
  open,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSaved?: (kit: BrandKit) => void;
}) {
  const catalog = useMotionGraphicsStore((s) => s.catalog);
  const [kit, setKit] = useState<BrandKit | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    motionGraphicsApi
      .brandKit()
      .then(setKit)
      .catch((err) => setError(getErrorMessage(err, 'Could not load the brand kit')));
  }, [open]);

  const setPalette = (key: keyof BrandKit['palette'], value: string) =>
    kit && setKit({ ...kit, palette: { ...kit.palette, [key]: value } });

  const save = async () => {
    if (!kit) return;
    const bad = SWATCH_KEYS.find(({ key }) => kit.palette[key] && !HEX.test(kit.palette[key] as string));
    if (bad) {
      setError(`${bad.label} must be a hex color like #1A2B3C.`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await motionGraphicsApi.saveBrandKit({
        name: kit.name,
        palette: kit.palette,
        fonts: kit.fonts,
        intensity: kit.intensity,
        use_brand_background: kit.use_brand_background,
        auto_apply: kit.auto_apply,
      });
      setKit(saved);
      onSaved?.(saved);
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the brand kit'));
    } finally {
      setSaving(false);
    }
  };

  const uploadLogo = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      setKit(await motionGraphicsApi.uploadLogo(file));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not upload the logo'));
    } finally {
      setUploading(false);
    }
  };

  const fonts = catalog?.fonts ?? [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Brand kit</DialogTitle>
          <DialogDescription>
            Logo, colors, fonts and motion feel. Text colors are adjusted automatically to stay readable.
          </DialogDescription>
        </DialogHeader>
        {!kit ? (
          <div className="shimmer h-64 rounded-lg" />
        ) : (
          <div className="space-y-5">
            <div>
              <FieldLabel htmlFor="mg-brand-name">Brand name</FieldLabel>
              <Input
                id="mg-brand-name"
                value={kit.name ?? ''}
                maxLength={80}
                onChange={(e) => setKit({ ...kit, name: e.target.value })}
              />
            </div>
            <div>
              <FieldLabel hint="PNG with transparency works best">Logo</FieldLabel>
              <div className="flex items-start gap-2">
                <MediaDropzone
                  kinds={['logo', 'image']}
                  accept="image/png,image/jpeg,image/webp"
                  icon={ImagePlus}
                  label="Add a logo"
                  hint="PNG, JPEG or WebP"
                  title="Add a logo"
                  disabled={uploading}
                  unusableReason={(a) => (a.contentType === 'image/svg+xml' ? 'SVG is not supported here, use PNG' : null)}
                  onFiles={(files) => uploadLogo(files[0])}
                  className="min-h-[120px] flex-1"
                >
                  {kit.logo_url || uploading ? (
                    <div className="flex flex-col items-center gap-2">
                      <div className="flex h-16 w-28 items-center justify-center overflow-hidden rounded-lg border border-border bg-secondary/40">
                        {uploading ? (
                          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Uploading" />
                        ) : (
                          <img src={kit.logo_url ?? undefined} alt="Brand logo" className="max-h-full max-w-full object-contain p-1" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">Drop or click to replace</p>
                    </div>
                  ) : undefined}
                </MediaDropzone>
                {kit.logo_url && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => setKit(await motionGraphicsApi.deleteLogo())}
                    aria-label="Remove logo"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {SWATCH_KEYS.map(({ key, label }) => (
                <div key={key}>
                  <FieldLabel htmlFor={`mg-sw-${key}`}>{label}</FieldLabel>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      aria-label={`${label} picker`}
                      value={HEX.test(kit.palette[key] ?? '') ? (kit.palette[key] as string) : '#808080'}
                      onChange={(e) => setPalette(key, e.target.value.toUpperCase())}
                      className="h-9 w-10 cursor-pointer rounded-md border border-border bg-transparent"
                    />
                    <Input
                      id={`mg-sw-${key}`}
                      value={kit.palette[key] ?? ''}
                      placeholder="Style default"
                      onChange={(e) => setPalette(key, e.target.value.trim())}
                      className="font-mono text-xs"
                    />
                  </div>
                </div>
              ))}
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Switch
                checked={kit.use_brand_background}
                onCheckedChange={(v) => setKit({ ...kit, use_brand_background: v })}
              />
              Use the brand background instead of the style's
            </label>
            <div className="grid grid-cols-2 gap-3">
              {(['display', 'text'] as const).map((role) => (
                <div key={role}>
                  <FieldLabel>{role === 'display' ? 'Headline font' : 'Body font'}</FieldLabel>
                  <Select
                    value={kit.fonts[role] ?? NONE}
                    onValueChange={(v) => setKit({ ...kit, fonts: { ...kit.fonts, [role]: v === NONE ? undefined : v } })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>Style default</SelectItem>
                      {fonts
                        .filter((f) => role === 'display' || !['Anton', 'Bebas Neue'].includes(f))
                        .map((f) => (
                          <SelectItem key={f} value={f}>
                            {f}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
            <p className="-mt-2 text-xs text-muted-foreground">
              Bundled fonts under the SIL Open Font License only; they are licensed for video and server rendering.
            </p>
            <div>
              <FieldLabel>Motion intensity</FieldLabel>
              <PillGroup<Intensity>
                value={kit.intensity}
                onChange={(v) => setKit({ ...kit, intensity: v })}
                options={[
                  { id: 'calm', label: 'Calm' },
                  { id: 'standard', label: 'Standard' },
                  { id: 'punchy', label: 'Punchy' },
                ]}
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Switch checked={kit.auto_apply} onCheckedChange={(v) => setKit({ ...kit, auto_apply: v })} />
              Apply to new projects automatically
            </label>
            {error && <ErrorNote>{error}</ErrorNote>}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={!kit || saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} {saving ? 'Saving' : 'Save brand kit'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
