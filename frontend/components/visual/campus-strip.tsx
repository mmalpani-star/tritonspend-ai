import type { ReactNode } from "react";
import type { CampusPhotoId } from "../../lib/campus-photos";
import { CampusPhoto } from "./campus-photo";
import { SpeckleField } from "./speckle-field";
import { SpectrumShape } from "./spectrum-shape";

/** Slim campus photo band with spectrum light, for page headers that should stay compact. */
export function CampusStrip({ photo, position = "object-center", children }: { photo: CampusPhotoId; position?: string; children: ReactNode }) {
  return (
    <section className="campus-strip">
      <div className="campus-strip-photo" aria-hidden="true">
        <CampusPhoto photo={photo} sizes="(min-width: 768px) 60vw, 100vw" decorative label className="h-full w-full" imageClassName={position} />
      </div>
      <SpectrumShape variant="orb" drift className="campus-strip-orb" />
      <SpeckleField edge="left" count={40} seed={53} className="campus-strip-speckles" />
      <div className="campus-strip-copy">{children}</div>
    </section>
  );
}
