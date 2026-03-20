/** Pure helpers for benchmark run form (unit-testable). */

export function isBenchmarkFormReady(
  datasetId: number | '',
  queryCaseId: number | '',
  pipelineConfigId: number | '',
): boolean {
  return (
    datasetId !== '' &&
    queryCaseId !== '' &&
    pipelineConfigId !== '' &&
    Number.isFinite(Number(datasetId)) &&
    Number.isFinite(Number(queryCaseId)) &&
    Number.isFinite(Number(pipelineConfigId))
  )
}
