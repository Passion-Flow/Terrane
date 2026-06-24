/** Wiki 子页 —— 复用 KbWiki。 */

import { KbWiki } from "@/components/KbWiki";
import { useKb } from "@/components/KbLayout";

export function WikiPage() {
  const { id, canEdit } = useKb();
  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl"><KbWiki kbId={id} canEdit={canEdit} /></div>
    </div>
  );
}
