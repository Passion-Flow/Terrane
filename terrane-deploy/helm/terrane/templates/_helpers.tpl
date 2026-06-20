{{- define "terrane.name" -}}terrane{{- end -}}
{{- define "terrane.fullname" -}}
{{- if contains "terrane" .Release.Name }}{{ .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}{{ printf "%s-terrane" .Release.Name | trunc 63 | trimSuffix "-" }}{{- end }}
{{- end -}}

{{- define "terrane.labels" -}}
helm.sh/chart: {{ printf "terrane-%s" .Chart.Version }}
app.kubernetes.io/name: terrane
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* image ref from a component's own image block: { repository, tag }.
     Usage: {{ include "terrane.image" .Values.server.image }} */}}
{{- define "terrane.image" -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}

{{- define "terrane.db.host" -}}
{{- if .Values.postgres.enabled }}{{ include "terrane.fullname" . }}-postgres{{ else }}{{ .Values.externalDatabase.host }}{{ end -}}
{{- end -}}
{{- define "terrane.db.port" -}}
{{- if .Values.postgres.enabled }}5432{{ else }}{{ .Values.externalDatabase.port }}{{ end -}}
{{- end -}}
{{- define "terrane.db.user" -}}
{{- if .Values.postgres.enabled }}{{ .Values.postgres.username }}{{ else }}{{ .Values.externalDatabase.username }}{{ end -}}
{{- end -}}
{{- define "terrane.db.sslmode" -}}
{{- if .Values.postgres.enabled }}disable{{ else }}{{ .Values.externalDatabase.sslMode }}{{ end -}}
{{- end -}}

{{- define "terrane.cache.host" -}}
{{- if .Values.redis.enabled }}{{ include "terrane.fullname" . }}-redis{{ else }}{{ .Values.externalRedis.host }}{{ end -}}
{{- end -}}
{{- define "terrane.cache.port" -}}
{{- if .Values.redis.enabled }}6379{{ else }}{{ .Values.externalRedis.port }}{{ end -}}
{{- end -}}
