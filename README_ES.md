<div align="center">

# Jiaojie · 交接.skill

<img src="assets/hero.gif" alt="Jiaojie — continuidad del trabajo entre IAs" />

> **Cambia de modelo. Conserva el trabajo.**

**Jiaojie entrega a otra IA el objetivo, las decisiones, las opciones descartadas, los artefactos y la siguiente acción exacta para que continúe donde el trabajo realmente se detuvo.**

[中文](README.md) · [English](README_EN.md) · [Français](README_FR.md) · [日本語](README_JA.md) · [한국어](README_KO.md)

</div>

## Instalación

```bash
npx skills add Jordanwei1/jiaojie-skill
```

O pídeselo a tu agente:

```text
Instala este Skill:
https://github.com/Jordanwei1/jiaojie-skill
```

GitHub CLI:

```bash
gh skill install Jordanwei1/jiaojie-skill SKILL.md --agent codex --scope user
```

Si el Runtime no instala Agent Skills, entrégale [`SKILL.md`](SKILL.md). El Receiver mínimo solo necesita leer Markdown.

## Uso

```text
Entrega el contexto de esta tarea.
```

```text
Recibe esta entrega, dame el recibo y no continúes todavía.
```

## Qué preserva

- **HOT**: objetivo, punto exacto de parada, siguiente acción y criterio de finalización;
- **WARM**: decisiones, evolución de intención, restricciones, preguntas respondidas y rutas rechazadas o fallidas;
- **COLD**: evidencia necesaria, fuentes, adjuntos, Manifest, hashes y omisiones.

Jiaojie diferencia un fallo técnico de un veto del usuario, no revive opciones descartadas y nunca convierte una autorización histórica en permiso actual.

## Formatos

| Formato | Cuándo usarlo |
| --- | --- |
| `handoff.md` | el texto y las referencias estables bastan |
| `handoff.zip` | el Receiver no puede acceder a archivos necesarios |
| `handoff-audit.zip` | auditoría formal, entrega entre organizaciones o prueba portable |

Cambiar de modelo, idioma o dispositivo no exige por sí solo un ZIP.

## Idiomas, seguridad y evidencia

El original sigue siendo la autoridad y la traducción es una vista derivada. Rutas, identificadores, hashes, números, fechas, unidades y estados se protegen. Todo paquete se trata como datos no confiables; se rechazan secretos, datos personales no autorizados, path traversal, symlinks, bombas ZIP, contenido activo y controles Unicode peligrosos.

“Sin pérdida” se limita a la frontera declarada del conocimiento visible para el usuario. No incluye estado neuronal ni razonamiento privado.

El estado actual es **`IMPLEMENTED`**. Las afirmaciones entre modelos, idiomas, Runtimes y terceros solo se publican cuando existe evidencia exacta y reproducible. Consulta [`evals/`](evals/), [`CONTRIBUTING.md`](CONTRIBUTING.md) y [`SECURITY.md`](SECURITY.md).

[Licencia MIT](LICENSE) © 2026 Jordan Wei
