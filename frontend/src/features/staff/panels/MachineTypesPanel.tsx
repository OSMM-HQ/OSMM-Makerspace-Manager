import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Badge, Skeleton } from '../../../components/ui';
import {
  collectionResults,
  createMachineType,
  getMachineTypes,
  machineKeys,
  updateMachineType,
  type MachineType,
} from '../machinesApi';

function CustomTypeRow({ makerspaceId, machineType }: { makerspaceId: number; machineType: MachineType }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(machineType.name);
  const [icon, setIcon] = useState(machineType.icon);
  const rename = useMutation({
    mutationFn: () => updateMachineType(makerspaceId, machineType.id, { name: name.trim(), icon: icon.trim() }),
    onSuccess: async (updated) => {
      setName(updated.name);
      setIcon(updated.icon);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: machineKeys.types(makerspaceId) }),
        queryClient.invalidateQueries({ queryKey: machineKeys.list(makerspaceId) }),
      ]);
    },
  });

  return (
    <form
      className='grid gap-2 border-t border-line p-3 first:border-t-0 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end'
      onSubmit={(event) => { event.preventDefault(); rename.mutate(); }}
    >
      <label className='grid gap-1 text-xs font-semibold text-muted'>
        Name
        <input className='desk-input' value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <label className='grid gap-1 text-xs font-semibold text-muted'>
        Icon
        <input className='desk-input' value={icon} onChange={(event) => setIcon(event.target.value)} placeholder='Optional icon' />
      </label>
      <button className='desk-button' type='submit' disabled={rename.isPending || !name.trim()}>
        {rename.isPending ? 'Saving...' : 'Rename'}
      </button>
      <p className='text-xs text-muted md:col-span-3'>Slug: {machineType.slug} (fixed)</p>
      {rename.error instanceof Error ? <p className='text-sm text-danger md:col-span-3'>{rename.error.message}</p> : null}
    </form>
  );
}

export function MachineTypesPanel({
  makerspaceId,
  canManageMachines,
}: {
  makerspaceId: number;
  canManageMachines: boolean;
}) {
  const queryClient = useQueryClient();
  const [slug, setSlug] = useState('');
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const machineTypes = useQuery({
    queryKey: machineKeys.types(makerspaceId),
    queryFn: () => getMachineTypes(makerspaceId),
    enabled: canManageMachines,
  });
  const create = useMutation({
    mutationFn: () => createMachineType(makerspaceId, {
      slug: slug.trim(),
      name: name.trim(),
      icon: icon.trim(),
    }),
    onSuccess: async () => {
      setSlug('');
      setName('');
      setIcon('');
      await queryClient.invalidateQueries({ queryKey: machineKeys.types(makerspaceId) });
    },
  });
  const types = collectionResults(machineTypes.data);

  if (!canManageMachines) return null;

  return (
    <details className='mb-4 overflow-hidden rounded-xl border border-line bg-panel'>
      <summary className='cursor-pointer bg-surface px-3 py-2 text-sm font-semibold text-ink'>Machine types</summary>
      <div className='grid gap-3 p-3'>
        <p className='text-sm text-muted'>Create makerspace-specific types or rename existing custom types. Built-in types stay fixed.</p>
        <form
          className='grid gap-2 rounded-xl border border-line bg-bg p-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end'
          onSubmit={(event) => { event.preventDefault(); create.mutate(); }}
        >
          <label className='grid gap-1 text-xs font-semibold text-muted'>
            Slug
            <input className='desk-input' value={slug} onChange={(event) => setSlug(event.target.value)} placeholder='laser-cutter' required />
          </label>
          <label className='grid gap-1 text-xs font-semibold text-muted'>
            Name
            <input className='desk-input' value={name} onChange={(event) => setName(event.target.value)} placeholder='Laser cutter' required />
          </label>
          <label className='grid gap-1 text-xs font-semibold text-muted'>
            Icon
            <input className='desk-input' value={icon} onChange={(event) => setIcon(event.target.value)} placeholder='Optional icon' />
          </label>
          <button className='desk-button-primary' type='submit' disabled={create.isPending || !slug.trim() || !name.trim()}>
            {create.isPending ? 'Creating...' : 'Create type'}
          </button>
          {create.error instanceof Error ? <p className='text-sm text-danger md:col-span-4'>{create.error.message}</p> : null}
        </form>

        {machineTypes.isLoading ? <Skeleton className='h-20 w-full' /> : null}
        {machineTypes.error instanceof Error ? <p className='text-sm text-danger'>{machineTypes.error.message}</p> : null}
        {types.length ? (
          <div className='overflow-hidden rounded-xl border border-line'>
            {types.map((machineType) => (
              machineType.is_builtin || machineType.makerspace === null ? (
                <div key={machineType.id} className='flex flex-wrap items-center justify-between gap-2 border-t border-line p-3 first:border-t-0'>
                  <span>
                    <strong className='block text-sm text-ink'>{machineType.name}</strong>
                    <span className='text-xs text-muted'>{machineType.icon || 'No icon'} · {machineType.slug}</span>
                  </span>
                  <Badge tone='neutral'>Built-in · read-only</Badge>
                </div>
              ) : (
                <CustomTypeRow key={machineType.id} makerspaceId={makerspaceId} machineType={machineType} />
              )
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}
