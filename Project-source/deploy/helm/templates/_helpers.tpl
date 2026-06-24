{{- define "terrane.labels" -}}
app.kubernetes.io/name: terrane
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
{{- define "terrane.pyenv" -}}
- { name: DATABASE_HOST, value: "{{ .Release.Name }}-postgres" }
- { name: DATABASE_PORT, value: "5432" }
- { name: DATABASE_USERNAME, value: "terrane_app" }
- { name: DATABASE_SSL_MODE, value: "disable" }
- { name: CACHE_HOST, value: "{{ .Release.Name }}-redis" }
- { name: CACHE_PORT, value: "6379" }
- name: DATABASE_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ .Release.Name }}-secrets, key: postgresPassword } }
- name: CACHE_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ .Release.Name }}-secrets, key: redisPassword } }
- name: TERRANE_KEK
  valueFrom: { secretKeyRef: { name: {{ .Release.Name }}-secrets, key: kek } }
- { name: LICENSE_REQUIRED, value: "{{ .Values.config.licenseRequired }}" }
- { name: TERRANE_FORGE_EDGE_URL, value: "{{ .Values.config.forgeEdgeUrl }}" }
- { name: SESSION_COOKIE_SECURE, value: "{{ .Values.config.sessionCookieSecure }}" }
{{- end -}}
