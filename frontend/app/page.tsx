import { QueryProvider } from "@/components/query-provider";
import { Workspace } from "@/components/workspace";

export default function Home() {
  return (
    <QueryProvider>
      <Workspace />
    </QueryProvider>
  );
}
