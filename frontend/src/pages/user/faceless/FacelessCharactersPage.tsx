import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Plus, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Stagger, StaggerItem } from '@/components/motion';
import { SEO } from '@/components/SEO';
import { getErrorMessage } from '@/utils/errors';
import { facelessApi, type FacelessCharacter } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { CatalogError } from '@/components/faceless/CatalogError';
import { CharacterCard } from '@/components/faceless/CharacterCard';
import { CharacterEditorDialog } from '@/components/faceless/CharacterEditorDialog';
import { EmptyState, ErrorNote, PageHeader, PillGroup } from '@/components/faceless/shared';

type View = 'active' | 'archived';

export function FacelessCharactersPage() {
  const { characters, charactersLoaded, voices, listError, loadCatalog, loadCharacters, upsertCharacter, removeCharacter } =
    useFacelessStore();
  const [view, setView] = useState<View>('active');
  const [editing, setEditing] = useState<FacelessCharacter | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [toDelete, setToDelete] = useState<FacelessCharacter | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCatalog();
    loadCharacters();
  }, [loadCatalog, loadCharacters]);

  const shown = characters.filter((c) => (view === 'archived' ? c.is_archived : !c.is_archived));
  const archivedCount = characters.filter((c) => c.is_archived).length;

  const openEditor = (c: FacelessCharacter | null) => {
    setEditing(c);
    setEditorOpen(true);
  };

  const toggleArchive = async (c: FacelessCharacter) => {
    setError(null);
    try {
      upsertCharacter(await facelessApi.updateCharacter(c.id, { is_archived: !c.is_archived }));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not update the character'));
    }
  };

  const remove = async () => {
    if (!toDelete) return;
    setError(null);
    try {
      await facelessApi.deleteCharacter(toDelete.id);
      removeCharacter(toDelete.id);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not delete the character'));
    }
  };

  return (
    <>
      <SEO title="Cast library" url="/faceless/characters" noindex />
      <Stagger className="w-full">
        <StaggerItem>
          <PageHeader
            title="Cast library"
            description="Recurring characters with a written bible, references and a voice. Up to six per episode."
            actions={
              <>
                <Button asChild variant="ghost">
                  <Link to="/faceless">
                    <ArrowLeft className="h-4 w-4" /> Studio
                  </Link>
                </Button>
                <Button onClick={() => openEditor(null)}>
                  <Plus className="h-4 w-4" /> New character
                </Button>
              </>
            }
          />
        </StaggerItem>

        <StaggerItem className="mb-5">
          <PillGroup<View>
            label="Show"
            value={view}
            onChange={setView}
            options={[
              { value: 'active', label: 'Active' },
              { value: 'archived', label: `Archived (${archivedCount})` },
            ]}
          />
        </StaggerItem>

        <StaggerItem>
          <CatalogError className="mb-5" />
        </StaggerItem>

        {(error || listError) && (
          <StaggerItem className="mb-5">
            <ErrorNote>{error || listError}</ErrorNote>
          </StaggerItem>
        )}

        <StaggerItem>
          {!charactersLoaded ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="shimmer aspect-[4/6] rounded-xl" />
              ))}
            </div>
          ) : shown.length === 0 ? (
            <EmptyState
              icon={Users}
              title={view === 'archived' ? 'Nothing archived' : 'No characters yet'}
              action={
                view === 'active' && (
                  <Button onClick={() => openEditor(null)}>
                    <Plus className="h-4 w-4" /> Create a character
                  </Button>
                )
              }
            >
              {view === 'active' &&
                'Upload two or three angles of a character, a short video, or just describe them. The studio writes a bible that keeps them consistent in every scene.'}
            </EmptyState>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {shown.map((c) => (
                <CharacterCard
                  key={c.id}
                  character={c}
                  voices={voices}
                  onEdit={openEditor}
                  onToggleArchive={toggleArchive}
                  onDelete={setToDelete}
                />
              ))}
            </div>
          )}
        </StaggerItem>
      </Stagger>

      <CharacterEditorDialog open={editorOpen} onOpenChange={setEditorOpen} character={editing} voices={voices} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Delete character"
        description={`Delete ${toDelete?.name ?? 'this character'} and its references? Projects that used them keep their finished scenes. Archive instead to hide them without losing anything.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={remove}
      />
    </>
  );
}
