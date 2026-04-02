"use client";

import { useEffect, useRef, useState, createContext, useContext } from "react";

// ── useInView ─────────────────────────────────────────────────────────────────
// Returns a ref to attach to a DOM element and a boolean indicating
// whether the element has entered the viewport.

export function useInView(options?: IntersectionObserverInit): {
  ref: React.RefObject<HTMLDivElement | null>;
  inView: boolean;
} {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect(); // fire once
        }
      },
      { threshold: 0.15, ...options }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [options]);

  return { ref, inView };
}

// ── PersonaContext ────────────────────────────────────────────────────────────
// Simple context for RECRUITER / ENGINEER toggle.
// Placed here so it can be imported by any component without circular deps.

export type Persona = "recruiter" | "engineer";

export const PersonaContext = createContext<{
  persona: Persona;
  setPersona: (p: Persona) => void;
}>({
  persona: "recruiter",
  setPersona: () => {},
});

export function usePersona() {
  return useContext(PersonaContext);
}
