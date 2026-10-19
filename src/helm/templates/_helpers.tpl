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
NERD0006 resource-output lookup (mirrors hmd_cli_helm._resource_output), scoped to one
dependency role: return the `output` of the first Resource in that role's `hmd_resources`
whose ResourceDefinition name matches, as JSON. Empty JSON object when none is present, so
callers can `fromJson` and test for keys and fall back to the cloud (dependency-chain) path.

Scoped to a role on purpose: a role receives every Resource its bound instance produced,
and other roles can carry Resources of the same type (the environment's shared postgres,
for one). Scanning every role let any of them supply this chart's values.

Usage: $ic := include "ns.resourceOutput" (dict "ctx" . "role" "eks-alb" "def" "ingress-controller") | fromJson
*/}}
{{- define "ns.resourceOutput" -}}
{{- $ctx := .ctx -}}
{{- $target := .def -}}
{{- $found := dict -}}
{{- $dep := index ($ctx.Values.dependencies | default dict) .role | default dict -}}
{{- $items := $dep -}}
{{- if not (kindIs "slice" $items) -}}{{- $items = list $items -}}{{- end -}}
{{- range $item := $items -}}
{{- if and (kindIs "map" $item) (not $found) -}}
{{- range $res := (index $item "hmd_resources" | default list) -}}
{{- $rd := (index $res "resource_definition") | default dict -}}
{{- if and (not $found) (eq (index $rd "resource_definition_name") $target) -}}
{{- $found = (index $res "output") | default dict -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- $found | toJson -}}
{{- end -}}

{{/*
The database account bound to the db-credentials role, as JSON `{secret_name, database_name}`;
an empty object means "use the cloud dependency chain" (db-credentials.dependencies.database-instance
plus details.<instance>.db_name). Fails the render rather than guessing:

- A `database-account` Resource (hmd-database-account), or a per-database `postgres` Resource
  (the legacy local dev_db.py producer), qualifies only with both `database_name` and
  `secret_name`. The environment's shared postgres (environment-db) carries the admin secret
  and no `database_name`, so it never qualifies -- binding it rendered an ExternalSecret on
  the admin credential and an empty DB_NAME, and the pods never started.
- Neither a qualifying Resource nor the cloud chain: nothing to build a secret name from.
*/}}
{{- define "ns.dbCredentials" -}}
{{- $dep := index (.Values.dependencies | default dict) "db-credentials" | default dict -}}
{{- $found := dict -}}
{{- $bound := list -}}
{{- range $res := (index $dep "hmd_resources" | default list) -}}
{{- $rd := (index $res "resource_definition") | default dict -}}
{{- $def := index $rd "resource_definition_name" | default "" -}}
{{- $out := (index $res "output") | default dict -}}
{{- $bound = append $bound (printf "%s (%s/%s; outputs: %s)" (index $res "resource_name" | default "?") (index $rd "resource_namespace" | default "?") $def (keys $out | sortAlpha | join ", ")) -}}
{{- if and (not $found) (has $def (list "database-account" "postgres")) $out.database_name $out.secret_name -}}
{{- $found = dict "secret_name" $out.secret_name "database_name" $out.database_name "kind" $def -}}
{{- end -}}
{{- end -}}
{{- if $found -}}
{{- $found | toJson -}}
{{- else -}}
{{- $dbInstance := index ($dep.dependencies | default dict) "database-instance" -}}
{{- $details := index (.Values.details | default dict) ($dep.instance_name | default "") | default dict -}}
{{- if and $dbInstance $details.db_name -}}
{{- dict | toJson -}}
{{- else if $bound -}}
{{- fail (printf "db-credentials: no bound Resource is a database account with database_name and secret_name. Bound: %s. A shared Postgres instance's Resource (admin credentials, no database_name) is not a per-app database -- bind db-credentials to an hmd-database-account instance." (join "; " $bound)) -}}
{{- else -}}
{{- fail "db-credentials: nothing bound. Expected a database-account Resource (hmd-database-account) in dependencies.db-credentials.hmd_resources, or the cloud chain dependencies.db-credentials.dependencies.database-instance with details.<instance>.db_name." -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Ingress class for the app's Ingress. Resource-first (NERD0006): the `ingress-controller`
Resource bound to the eks-alb role supplies its `ingress_class` (e.g. the local k3s
Traefik's `traefik`); else fall back to `.Values.alb.className` (default "alb" for the
cloud AWS Load Balancer Controller). Lets one chart target either controller.
*/}}
{{- define "ns.ingressClass" -}}
{{- $ic := include "ns.resourceOutput" (dict "ctx" . "role" "eks-alb" "def" "ingress-controller") | fromJson -}}
{{- if $ic.ingress_class -}}
{{- $ic.ingress_class -}}
{{- else -}}
{{- .Values.alb.className | default "alb" -}}
{{- end -}}
{{- end -}}

{{/*
Kubernetes secret name for database credentials, synced by hmd-db-external-secret.yaml.
Resource-first (NERD0006): when ns.dbCredentials finds the db-credentials account Resource,
use a stable chart-scoped name; otherwise the cloud db-credentials chain, so cloud deploys
are unchanged.
*/}}
{{- define "k8sDbSecretName" -}}
{{- $db := include "ns.dbCredentials" . | fromJson -}}
{{- if $db.secret_name -}}
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
Secrets-manager key holding the DB credential. Resource-first: the db-credentials account
Resource's `output.secret_name`; else the cloud underscore-separated db-credentials chain.
*/}}
{{- define "awsDbSecretName" -}}
{{- $db := include "ns.dbCredentials" . | fromJson -}}
{{- if $db.secret_name -}}
{{- $db.secret_name -}}
{{- else -}}
{{- $dbCredentialsInstance := index .Values "dependencies" "db-credentials" "instance_name" -}}
{{ index .Values "dependencies" "db-credentials" "dependencies" "database-instance" "instance_name" }}_{{ index .Values "dependencies" "db-credentials" "dependencies" "database-instance" "repo_name" }}_{{ index .Values "dependencies" "db-credentials" "dependencies" "database-instance" "deployment_id" }}_{{ .Values.env.HMD_ENVIRONMENT }}_{{ .Values.env.HMD_REGION }}_{{ .Values.env.HMD_CUSTOMER_CODE }}_{{ index .Values "details" $dbCredentialsInstance "db_name" }}
{{- end -}}
{{- end -}}

{{/*
ClusterSecretStore the DB credential is read through. Where the secret lives depends on
who wrote it:

- A `database-account` Resource: hmd-ms-dbaccount wrote it with hmd_lib_secrets_backend,
  which stores account secrets in SSM Parameter Store (and migrates older Secrets Manager
  copies there on every create). Reading it through the Secrets Manager store gives
  "Secret does not exist" although the account exists (relpub, 2026-10-14).
- The cloud dependency chain: unchanged (ns.secretStoreName), unless
  `platformSecretStore=parameterStoreSecretStore` -- the same knob hmd-inf-hive-metastore
  uses for an environment whose account secrets exist only in Parameter Store.
- A legacy per-database `postgres` Resource (dev_db.py): Secrets Manager, as before.

Parameter Store name: `.Values.parameterStoreSecretStore.name`, else the ext-secrets
dependency's detail, else hmd-inf-ext-secrets' default `aws-parameter-store`.
*/}}
{{- define "ns.dbSecretStoreName" -}}
{{- $db := include "ns.dbCredentials" . | fromJson -}}
{{- if or (eq ($db.kind | default "") "database-account") (and (not $db.secret_name) (eq (.Values.platformSecretStore | default "") "parameterStoreSecretStore")) -}}
{{- $name := "" -}}
{{- if .Values.parameterStoreSecretStore -}}{{- $name = .Values.parameterStoreSecretStore.name | default "" -}}{{- end -}}
{{- if not $name -}}
{{- $extSecrets := index (.Values.dependencies | default dict) "ext-secrets" | default dict -}}
{{- $details := index (.Values.details | default dict) ($extSecrets.instance_name | default "") | default dict -}}
{{- $name = (index $details "parameterStoreSecretStore" | default dict).name | default "aws-parameter-store" -}}
{{- end -}}
{{- $name -}}
{{- else -}}
{{- include "ns.secretStoreName" . -}}
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
