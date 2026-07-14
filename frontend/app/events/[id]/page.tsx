import Link from "next/link";
import {
  getEvent,
  getEventExposures,
  getEventImplications,
  getEventSources,
  getHealth,
} from "@/lib/api";
import { EventDetail } from "@/components/EventDetail";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EventDetailPage({ params }: PageProps) {
  const { id } = await params;

  let event;
  let sources;
  let exposures;
  let implications;
  let showcaseMode = false;

  try {
    const [eventData, sourcesData, exposuresData, implicationsData, health] =
      await Promise.all([
        getEvent(id),
        getEventSources(id),
        getEventExposures(id),
        getEventImplications(id),
        getHealth(),
      ]);
    event = eventData;
    sources = sourcesData;
    exposures = exposuresData.items;
    implications = implicationsData.items;
    showcaseMode = health.showcase_mode ?? false;
  } catch {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        Event nicht gefunden oder API nicht erreichbar.
        <Link href="/events" className="ml-2 font-medium underline">
          Zurück zur Liste
        </Link>
      </div>
    );
  }

  return (
    <EventDetail
      event={event}
      sources={sources}
      exposures={exposures}
      implications={implications}
      showcaseMode={showcaseMode}
    />
  );
}
