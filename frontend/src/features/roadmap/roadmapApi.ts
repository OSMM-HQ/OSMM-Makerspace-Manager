import { useQuery } from "@tanstack/react-query";

import { MakerspaceApiClient } from "../../generated/api";
import { API_V1_URL } from "../../lib/api";

export type PublicRoadmapItem = {
  title: string;
  description: string;
  status: "shipped" | "in_progress" | "planned";
  category: string;
  published_at: string | null;
};

const roadmapClient = new MakerspaceApiClient(API_V1_URL);

export function usePublicRoadmap() {
  return useQuery({
    queryKey: ["public-roadmap"],
    queryFn: () =>
      roadmapClient.request<PublicRoadmapItem[]>("/public/roadmap"),
  });
}
