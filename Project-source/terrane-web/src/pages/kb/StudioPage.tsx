/** Studio subpage — reuses StudioPanel. */

import { StudioPanel } from "@/components/StudioPanel";
import { useKb } from "@/components/KbLayout";

export function StudioPage() {
  const { id } = useKb();
  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl"><StudioPanel kbId={id} /></div>
    </div>
  );
}
