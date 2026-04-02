"use client";

import { useState } from "react";
import { PersonaContext, type Persona } from "@/lib/hooks";

export function PersonaProvider({ children }: { children: React.ReactNode }) {
  const [persona, setPersona] = useState<Persona>("recruiter");

  return (
    <PersonaContext.Provider value={{ persona, setPersona }}>
      {children}
    </PersonaContext.Provider>
  );
}
