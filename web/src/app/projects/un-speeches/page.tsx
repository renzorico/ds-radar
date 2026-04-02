import type { Metadata } from "next";
import { projects } from "@/data/projects";
import ProjectDetailClient from "@/components/ProjectDetailClient";

export const metadata: Metadata = {
  title: "UN Speeches — Renzo Rico",
  description:
    "Topic modeling 70 years of UN General Assembly debate. BERTopic + LDA + HuggingFace.",
};

export default function UnSpeechesPage() {
  const project = projects.find((p) => p.id === "un-speeches")!;
  return <ProjectDetailClient project={project} />;
}
