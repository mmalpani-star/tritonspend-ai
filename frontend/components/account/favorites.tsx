"use client";

import { Heart } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { readFavorites, setFavorite } from "../../lib/api";
import { FavoriteKind, Favorites, favoriteButtonLabel, isFavorite, withoutFavorite } from "../../lib/account";

type FavoritesState = {
  favorites: Favorites | null;
  error: string | null;
  isSaved: (kind: FavoriteKind, id: string) => boolean;
  isPending: (kind: FavoriteKind, id: string) => boolean;
  /** Saves or removes; rejects with a readable message if the server refuses. */
  toggle: (kind: FavoriteKind, id: string) => Promise<void>;
  reload: () => Promise<void>;
};

const FavoritesContext = createContext<FavoritesState | null>(null);
const key = (kind: FavoriteKind, id: string) => `${kind}:${id}`;

/** The signed-in student's saved venues and dishes, loaded once and shared by every page. */
export function FavoritesProvider({ children }: { children: React.ReactNode }) {
  const [favorites, setFavorites] = useState<Favorites | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const current = useRef<Favorites | null>(null);
  current.current = favorites;

  const reload = useCallback(async () => {
    try {
      setFavorites(await readFavorites());
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Couldn't load your favourites.");
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  const toggle = useCallback(async (kind: FavoriteKind, id: string) => {
    const saved = !isFavorite(current.current, kind, id);
    setPending((value) => new Set(value).add(key(kind, id)));
    try {
      await setFavorite(kind, id, saved);
      if (saved) await reload(); // the list needs the full record (name, rating) from the server
      else setFavorites((value) => (value ? withoutFavorite(value, kind, id) : value));
    } finally {
      setPending((value) => {
        const next = new Set(value);
        next.delete(key(kind, id));
        return next;
      });
    }
  }, [reload]);

  const value: FavoritesState = {
    favorites,
    error,
    isSaved: (kind, id) => isFavorite(favorites, kind, id),
    isPending: (kind, id) => pending.has(key(kind, id)),
    toggle,
    reload
  };
  return <FavoritesContext.Provider value={value}>{children}</FavoritesContext.Provider>;
}

export function useFavorites(): FavoritesState | null {
  return useContext(FavoritesContext);
}

/** A heart toggle for a venue or dish. Renders nothing outside a signed-in page. */
export function FavoriteButton({ kind, id, name, withLabel = false }: { kind: FavoriteKind; id: string; name: string; withLabel?: boolean }) {
  const favorites = useFavorites();
  const [problem, setProblem] = useState("");
  if (!favorites) return null;
  const saved = favorites.isSaved(kind, id);
  const busy = favorites.isPending(kind, id) || (favorites.favorites === null && !favorites.error);
  const label = favoriteButtonLabel(saved, name);

  async function click() {
    setProblem("");
    try {
      await favorites!.toggle(kind, id);
    } catch (failure) {
      setProblem(failure instanceof Error ? failure.message : "Couldn't update your favourites.");
    }
  }

  return (
    <span className="favorite-wrap">
      <button
        type="button"
        className={`favorite-button ${saved ? "favorite-button-on" : ""} ${withLabel ? "favorite-button-labelled" : ""}`}
        aria-pressed={saved}
        aria-label={withLabel ? undefined : label}
        title={label}
        disabled={busy}
        onClick={() => void click()}
      >
        <Heart size={16} aria-hidden="true" fill={saved ? "currentColor" : "none"} />
        {withLabel && <span>{saved ? "Saved" : "Save"}</span>}
      </button>
      {problem && <span role="alert" className="favorite-problem">{problem}</span>}
    </span>
  );
}
