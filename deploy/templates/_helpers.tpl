{{/* Labels shared by every object; a component label is added per object. */}}
{{- define "release-notes.labels" -}}
app.kubernetes.io/name: release-notes
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
