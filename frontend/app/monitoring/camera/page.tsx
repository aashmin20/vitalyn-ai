import { redirect } from "next/navigation";

// Live Camera was merged into Watch Live: select a patient and their registered camera opens.
export default function LiveCameraRedirect() {
  redirect("/monitoring/watch");
}
