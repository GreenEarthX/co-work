import { useEffect, useMemo, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { safeGetItem, safeSetItem } from "@/lib/safeStorage";
import { scenarios, type ScenarioData } from "@/lib/scenarioData";

export const DEFAULT_PLANT_ID = "rotterdam-rfnbo";
const LAST_ACTIVE_PLANT_KEY = "dashboard:lastPlantId";

const DEFAULT_SCENARIO_ID = "base";

function getScenarioById(id: string): ScenarioData {
  return (
    scenarios.find((s: ScenarioData) => s.id === id) ??
    scenarios.find((s: ScenarioData) => s.id === DEFAULT_SCENARIO_ID) ??
    scenarios[0]
  );
}

export function useActivePlantId(): string {
  const params = useParams();
  const location = useLocation();

  const routePlantId = (params.plantId || params.projectId) as string | undefined;

  const pathPlantId = useMemo(() => {
    const segments = location.pathname.split("/").filter(Boolean);
    const [section, value] = segments;
    if (["plant", "canvas", "project", "cost-structure", "regulatory", "policy", "procurement", "procurement-strategy", "project-finance", "project-hub"].includes(section) && value && value !== "access") {
      return value;
    }
    return undefined;
  }, [location.pathname]);

  const [storedPlantId, setStoredPlantId] = useState<string>(() => {
    return safeGetItem(LAST_ACTIVE_PLANT_KEY) || DEFAULT_PLANT_ID;
  });

  const activePlantId = routePlantId || pathPlantId || storedPlantId || DEFAULT_PLANT_ID;

  useEffect(() => {
    if (!activePlantId) return;

    safeSetItem(LAST_ACTIVE_PLANT_KEY, activePlantId);
    setStoredPlantId(activePlantId);
  }, [activePlantId]);

  // React to storage updates from elsewhere (e.g. ProjectSwitcher changing
  // plant on routes that don't carry a plantId in the URL, like
  // /green-assets / Project Commercial). The native `storage` event only
  // fires across tabs, so the switcher dispatches a same-tab CustomEvent.
  useEffect(() => {
    const sync = () => {
      const v = safeGetItem(LAST_ACTIVE_PLANT_KEY);
      if (v) setStoredPlantId(v);
    };
    const onCustom = () => sync();
    const onStorage = (e: StorageEvent) => {
      if (e.key === LAST_ACTIVE_PLANT_KEY) sync();
    };
    window.addEventListener("active-plant-changed", onCustom);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("active-plant-changed", onCustom);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return activePlantId;
}

export function useProjectScenario(plantId: string): [ScenarioData, (scenario: ScenarioData) => void] {
  const storageKey = `dashboard:scenario:${plantId}`;
  const [scenarioId, setScenarioId] = useState<string>(() => {
    return safeGetItem(storageKey) || DEFAULT_SCENARIO_ID;
  });

  useEffect(() => {
    const persisted = safeGetItem(storageKey);
    if (persisted && persisted !== scenarioId) {
      setScenarioId(persisted);
    }
  }, [storageKey, scenarioId]);

  const selectedScenario = useMemo(() => getScenarioById(scenarioId), [scenarioId]);

  const setScenario = (next: ScenarioData) => {
    setScenarioId(next.id);
    safeSetItem(storageKey, next.id);
  };

  return [selectedScenario, setScenario];
}
