{{/*
Expand the name of the chart.
*/}}
{{- define "hmd-app-neuronsphere.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "hmd-app-neuronsphere.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "hmd-app-neuronsphere.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "hmd-app-neuronsphere.labels" -}}
helm.sh/chart: {{ include "hmd-app-neuronsphere.chart" . }}
{{ include "hmd-app-neuronsphere.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "hmd-app-neuronsphere.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hmd-app-neuronsphere.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "hmd-app-neuronsphere.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "hmd-app-neuronsphere.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
NERD0006 resource-output lookup (mirrors hmd_cli_helm._resource_output): walk every
dependency role's produced `hmd_resources` and return the `output` of the first Resource
whose ResourceDefinition name matches, as JSON. Empty JSON object when none is present, so
callers can `fromJson` and test for keys and fall back to the cloud (dependency-chain) path.

Usage: $pg := include "ns.resourceOutput" (dict "ctx" . "def" "postgres") | fromJson
*/}}
{{- define "ns.resourceOutput" -}}
{{- $ctx := .ctx -}}
{{- $target := .def -}}
{{- $found := dict -}}
{{- range $role, $dep := ($ctx.Values.dependencies | default dict) -}}
{{- $items := $dep -}}
{{- if not (kindIs "slice" $items) -}}{{- $items = list $items -}}{{- end -}}
{{- range $item := $items -}}
{{- if kindIs "map" $item -}}
{{- range $res := (index $item "hmd_resources" | default list) -}}
{{- $rd := (index $res "resource_definition") | default dict -}}
{{- if eq (index $rd "resource_definition_name") $target -}}
{{- $found = (index $res "output") | default dict -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- $found | toJson -}}
{{- end -}}

{{/*
Ingress class for the app's Ingress. Resource-first (NERD0006): the `ingress-controller`
Resource bound to the eks-alb role supplies its `ingress_class` (e.g. the local k3s
Traefik's `traefik`); else fall back to `.Values.alb.className` (default "alb" for the
cloud AWS Load Balancer Controller). Lets one chart target either controller.
*/}}
{{- define "ns.ingressClass" -}}
{{- $ic := include "ns.resourceOutput" (dict "ctx" . "def" "ingress-controller") | fromJson -}}
{{- if $ic.ingress_class -}}
{{- $ic.ingress_class -}}
{{- else -}}
{{- .Values.alb.className | default "alb" -}}
{{- end -}}
{{- end -}}

{{/*
Kubernetes secret name for database credentials, synced by hmd-db-external-secret.yaml.
Resource-first (NERD0006): when a `postgres` Resource is bound to the db-credentials role,
use a stable chart-scoped name; otherwise fall back to the cloud db-credentials chain so
cloud deploys are unchanged.
*/}}
{{- define "k8sDbSecretName" -}}
{{- $pg := include "ns.resourceOutput" (dict "ctx" . "def" "postgres") | fromJson -}}
{{- if $pg.secret_name -}}
{{- printf "%s-db" (include "hmd-app-neuronsphere.fullname" .) -}}
{{- else -}}
{{- $dbCredentialsInstance := index .Values "dependencies" "db-credentials" "instance_name" -}}
{{- $dbInstance := index .Values "dependencies" "db-credentials" "dependencies" "database-instance" -}}
{{- $dbName := index .Values "details" $dbCredentialsInstance "db_name" -}}
{{- /* K8s object names must be RFC 1123 (lowercase, no underscores); db_name
       legitimately uses underscores (Postgres) so sanitize here only -- the AWS
       secret name (awsDbSecretName) keeps the raw underscores. No-op for names
       already valid, so cloud behavior is unchanged. Without this, a db_name
       such as `deployment_gui` renders an ExternalSecret the API server
       rejects, and the whole release fails. Mirrors hmd-inf-hive-metastore. */ -}}
{{- printf "%s-%s-%s-%s-%s-%s-%s" (index $dbInstance "instance_name") (index $dbInstance "repo_name") (index $dbInstance "deployment_id") .Values.env.HMD_ENVIRONMENT .Values.env.HMD_REGION .Values.env.HMD_CUSTOMER_CODE $dbName | replace "_" "-" | lower -}}
{{- end -}}
{{- end -}}

{{/*
Secrets-manager key holding the DB credential. Resource-first: the postgres Resource's
`output.secret_name`; else the cloud underscore-separated db-credentials chain.
*/}}
{{- define "awsDbSecretName" -}}
{{- $pg := include "ns.resourceOutput" (dict "ctx" . "def" "postgres") | fromJson -}}
{{- if $pg.secret_name -}}
{{- $pg.secret_name -}}
{{- else -}}
{{- $dbCredentialsInstance := index .Values "dependencies" "db-credentials" "instance_name" -}}
{{ index .Values "dependencies" "db-credentials" "dependencies" "database-instance" "instance_name" }}_{{ index .Values "dependencies" "db-credentials" "dependencies" "database-instance" "repo_name" }}_{{ index .Values "dependencies" "db-credentials" "dependencies" "database-instance" "deployment_id" }}_{{ .Values.env.HMD_ENVIRONMENT }}_{{ .Values.env.HMD_REGION }}_{{ .Values.env.HMD_CUSTOMER_CODE }}_{{ index .Values "details" $dbCredentialsInstance "db_name" }}
{{- end -}}
{{- end -}}

{{/*
Cluster secret store name for the ExternalSecrets. Prefer an explicit
`.Values.clusterSecretStore.name` (local sets this to the working local store); else the
ext-secrets dependency's resolved detail (cloud).
*/}}
{{- define "ns.secretStoreName" -}}
{{- if and .Values.clusterSecretStore .Values.clusterSecretStore.name -}}
{{- .Values.clusterSecretStore.name -}}
{{- else -}}
{{- $extSecretsInstanceName := index .Values "dependencies" "ext-secrets" "instance_name" -}}
{{- $extSecretsDetails := index .Values "details" $extSecretsInstanceName -}}
{{- $extSecretsDetails.clusterSecretStore.name -}}
{{- end -}}
{{- end -}}

{{/*
Resolve a short Okta group slug (e.g. "admin") to the full Okta group name
produced by CDKTF, mirroring hmd_lib_okta.groups.group_name:
  base   = title(lower(replace("_"/"-" -> " ", "<instance_name> <slug>")))
  name   = "NeuronSphere <base> - <title(lower(<environment>))>"
  if "hmd" in <customer_code>: name = "<name> (<customer_code>)"

Usage: include "ns.oktaGroupName" (dict "slug" "admin" "ctx" $)
*/}}
{{- define "ns.oktaGroupName" -}}
{{- $slug := .slug -}}
{{- $ctx := .ctx -}}
{{- $instance := index $ctx.Values "dependencies" "okta-app" "instance_name" -}}
{{- $env := $ctx.Values.env.HMD_ENVIRONMENT -}}
{{- $customer := $ctx.Values.env.HMD_CUSTOMER_CODE -}}
{{- $base := printf "%s %s" $instance $slug | replace "-" " " | replace "_" " " | lower | title -}}
{{- $envTitle := $env | lower | title -}}
{{- $name := printf "NeuronSphere %s - %s" $base $envTitle -}}
{{- if contains "hmd" $customer -}}
{{- printf "%s (%s)" $name $customer -}}
{{- else -}}
{{- $name -}}
{{- end -}}
{{- end -}}

{{/*
Resolve the comma-separated `config.oktaSuperuserGroups` value (a list of short
slugs like "admin" or "admin,super") to the full Okta group names CDKTF actually
creates. An entry containing a space is treated as an already-resolved literal
name and passed through unchanged (escape hatch for org-managed groups).

Usage: include "ns.oktaSuperuserGroupsResolved" $
*/}}
{{- define "ns.oktaSuperuserGroupsResolved" -}}
{{- $ctx := . -}}
{{- $raw := $ctx.Values.config.oktaSuperuserGroups | default "" -}}
{{- $resolved := list -}}
{{- range $entry := splitList "," $raw -}}
{{- $entry = trim $entry -}}
{{- if $entry -}}
{{- if contains " " $entry -}}
{{- $resolved = append $resolved $entry -}}
{{- else -}}
{{- $resolved = append $resolved (include "ns.oktaGroupName" (dict "slug" $entry "ctx" $ctx)) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- join "," $resolved -}}
{{- end -}}

{{/*
Redis in-cluster service host for the `redis` dependency (legacy repo_class_name —
hmd-inf-redis doesn't declare a BACON resource). Mirrors hmd-ms-transform's and
hmd-app-airflow's identically-named `redisHost` helper so all three chart consume
hmd-inf-redis the same way.
*/}}
{{- define "redisHost" -}}
{{- $redis := index .Values "dependencies" "redis" -}}
{{ $redis.instance_name }}-{{ $redis.deployment_id }}-{{ $redis.repo_name }}-master.{{ $redis.instance_name }}-{{ $redis.deployment_id }}.svc.cluster.local
{{- end -}}

{{- define "redisPort" -}}
6379
{{- end -}}

{{/*
Secrets-manager key holding the Redis credentials (username/password), synced into
a k8s Secret by redis-external-secret.yaml. Mirrors hmd-ms-transform's/
hmd-app-airflow's `redisSecretName` helper.
*/}}
{{- define "redisSecretName" -}}
{{ index .Values "dependencies" "redis" "instance_name" }}_{{ index .Values "dependencies" "redis" "repo_name" }}_{{ index .Values "dependencies" "redis" "deployment_id" }}_{{ .Values.env.HMD_ENVIRONMENT }}_{{ .Values.env.HMD_REGION }}_{{ .Values.env.HMD_CUSTOMER_CODE }}
{{- end -}}
