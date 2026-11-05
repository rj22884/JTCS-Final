export type ContactSort = "name" | "mobile" | "deleted";

export type SortableContact = {
  id: string;
  name: string;
  mobile: string;
  fullMobile: string;
  phoneKey: string;
  deletedAt: string | null;
};

/** Active-first for name sort; deleted-first for deleted sort; mobile uses number order. */
export function sortContacts<T extends SortableContact>(contacts: T[], mode: ContactSort = "name"): T[] {
  return [...contacts].sort((left, right) => {
    if (mode === "deleted") {
      const leftDeleted = left.deletedAt ? 0 : 1;
      const rightDeleted = right.deletedAt ? 0 : 1;
      if (leftDeleted !== rightDeleted) return leftDeleted - rightDeleted;
    } else if (mode === "name") {
      const leftDeleted = left.deletedAt ? 1 : 0;
      const rightDeleted = right.deletedAt ? 1 : 0;
      if (leftDeleted !== rightDeleted) return leftDeleted - rightDeleted;
    }
    if (mode === "mobile") {
      const byMobile = (left.phoneKey || left.fullMobile || left.mobile).localeCompare(
        right.phoneKey || right.fullMobile || right.mobile,
        undefined,
        { numeric: true },
      );
      if (byMobile !== 0) return byMobile;
    } else {
      const byName = left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
      if (byName !== 0) return byName;
    }
    return left.id.localeCompare(right.id);
  });
}
