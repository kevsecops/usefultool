import { notFound } from "next/navigation";
import { getAlert, ApiError } from "@/lib/api";
import { AlertDetail } from "@/components/AlertDetail";

export const dynamic = "force-dynamic";

interface AlertDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function AlertDetailPage({ params }: AlertDetailPageProps) {
  const { id } = await params;

  try {
    const alert = await getAlert(id);
    return <AlertDetail alert={alert} />;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      notFound();
    }
    throw e;
  }
}
