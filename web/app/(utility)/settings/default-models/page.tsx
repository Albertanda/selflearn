"use client";

import { useTranslation } from "react-i18next";

import DefaultModelsEditor from "@/components/settings/DefaultModelsEditor";
import { SettingsPageHeader } from "@/components/settings/shared";

export default function DefaultModelsSettingsPage() {
  const { t } = useTranslation();
  return (
    <div>
      <SettingsPageHeader
        title={t("Default models")}
        description={t(
          "Choose the saved reference each service uses when a request does not name a model. This page changes defaults only; it never saves other pages' unfinished edits.",
        )}
      />
      <DefaultModelsEditor />
    </div>
  );
}
