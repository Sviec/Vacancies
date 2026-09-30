/**
 * Короткие имена поверх сгенерированных типов OpenAPI.
 *
 * `schema.gen.ts` руками не правится: после изменения бэкенда — `npm run gen:api`.
 * Здесь только алиасы и то, чего в OpenAPI нет (форма `score_details`).
 */

import type { components, operations } from "@/api/schema.gen";

type Schemas = components["schemas"];

export type VacancyListItem = Schemas["VacancyListItem"];
export type VacancyDetail = Schemas["VacancyDetailRead"];
export type VacancyPostingBrief = Schemas["VacancyPostingBriefRead"];
export type VacancyListResponse = Schemas["PaginatedResponse_VacancyListItem_"];
export type FiltersMeta = Schemas["VacancyFiltersMeta"];
export type VacancyUserState = Schemas["VacancyUserState"];
export type UserAction = Schemas["UserAction"];
export type WorkFormat = Schemas["WorkFormat"];
export type ExperienceLevel = Schemas["ExperienceLevel"];
export type EmploymentType = Schemas["EmploymentType"];
export type SalaryPeriod = Schemas["SalaryPeriod"];
export type ParseQuality = Schemas["ParseQuality"];
export type VacancySort = Schemas["VacancySort"];
export type MatchDetails = Schemas["MatchDetails"];
export type MatchCriterionBreakdown = Schemas["MatchCriterionBreakdown"];
export type MatchSkillsBreakdown = Schemas["MatchSkillsBreakdown"];

export type ResumeRead = Schemas["ResumeRead"];
export type ResumeListItem = Schemas["ResumeListItem"];
export type ResumeListResponse = Schemas["ResumeListResponse"];
export type ResumeCreate = Schemas["ResumeCreate"];
export type ResumeUpdate = Schemas["ResumeUpdate"];
export type ResumeOrigin = Schemas["ResumeOrigin"];
export type ScoreCriterionDetail = Schemas["ScoreCriterionDetail"];
export type ScoreCriterionKey = Schemas["ScoreCriterionKey"];
export type ResumeScoreResponse = Schemas["ResumeScoreResponse"];
export type LanguageLevel = Schemas["LanguageLevel"];

export type SourceListItem = Schemas["SourceListItem"];
export type SourceListResponse = Schemas["SourceListResponse"];
export type SourceType = Schemas["SourceType"];
export type ParseRunRead = Schemas["ParseRunRead"];
export type ParseRunListResponse = Schemas["ParseRunListResponse"];
export type RunStatus = Schemas["RunStatus"];

export type HealthResponse = Schemas["HealthResponse"];
export type CheckResult = Schemas["CheckResult"];

/** Query-параметры ленты `GET /api/v1/vacancies`. */
export type VacancyListParams = NonNullable<
  operations["list_vacancies_api_v1_vacancies_get"]["parameters"]["query"]
>;

/** Query-параметры истории запусков `GET /api/v1/sources/runs`. */
export type RunListParams = NonNullable<
  operations["list_runs_api_v1_sources_runs_get"]["parameters"]["query"]
>;

/**
 * Форма JSONB `resumes.score_details` (`ResumeScoreDetails` на бэкенде).
 * В OpenAPI поле описано как свободный словарь, поэтому тип ручной.
 */
export interface ResumeScoreDetails {
  version: 1;
  score: number;
  criteria: ScoreCriterionDetail[];
  recommendations: string[];
  market: {
    basis: "target_position" | "all_vacancies" | "none";
    sample_size: number;
    top_skills: string[];
  };
}

const CRITERIA_COUNT = 8;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isCriterion(value: unknown): value is ScoreCriterionDetail {
  return (
    isRecord(value) &&
    typeof value.key === "string" &&
    typeof value.name === "string" &&
    typeof value.weight === "number" &&
    typeof value.points === "number" &&
    (value.recommendation === undefined ||
      value.recommendation === null ||
      typeof value.recommendation === "string")
  );
}

/** Проверить форму `score_details`; битая или старая версия — `null`. */
export function parseScoreDetails(raw: unknown): ResumeScoreDetails | null {
  if (!isRecord(raw) || raw.version !== 1 || typeof raw.score !== "number") {
    return null;
  }
  const { criteria, recommendations, market } = raw;
  if (
    !Array.isArray(criteria) ||
    criteria.length !== CRITERIA_COUNT ||
    !criteria.every(isCriterion) ||
    !isStringArray(recommendations) ||
    !isRecord(market) ||
    typeof market.sample_size !== "number" ||
    !isStringArray(market.top_skills) ||
    (market.basis !== "target_position" &&
      market.basis !== "all_vacancies" &&
      market.basis !== "none")
  ) {
    return null;
  }
  return raw as unknown as ResumeScoreDetails;
}
