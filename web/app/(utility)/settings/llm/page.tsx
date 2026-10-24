"use client";

import { useTranslation } from "react-i18next";

import { ServiceConfigEditor } from "@/components/settings/ServiceConfigEditor";
import { SettingsPageHeader } from "@/components/settings/shared";

export default function LlmSettingsPage() {
  const { t } = useTranslation();
  return (
    <div>
      <SettingsPageHeader
        title={t("Large language model (LLM)")}
        description={t(
          "Configure language model connections and models. Browsing or editing here never changes the saved default model; use Default models for that.",
        )}
      />
      <ServiceConfigEditor service="llm" />
    </div>
  );
}
