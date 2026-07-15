import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { queryClient } from "@/api/queryClient";
import { router } from "@/routes/router";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { Toaster } from "@/components/ui/sonner";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorModalProvider>
        <RouterProvider router={router} />
        <Toaster position="top-center" />
      </ErrorModalProvider>
    </QueryClientProvider>
  );
}

export default App;
