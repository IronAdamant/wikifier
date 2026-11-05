//! MCP tool groups, chosen per project by an agent (the `agent-tools` block in AGENTS.md)
//! or by the operator (`WIKIFIER_TOOLS` / `WIKIFIER_DISABLE`, which win per key).
//! The suite-wide convention: every tool is in one group, `core` is always on, an env
//! mistake stops the server, a block mistake is a warning, and with no switch and no
//! block nothing changes.

use std::collections::BTreeSet;

use crate::api::MCP_TOOLS;

pub const TOOLS_VAR: &str = "WIKIFIER_TOOLS";
pub const DISABLE_VAR: &str = "WIKIFIER_DISABLE";

/// Every MCP tool, by group. `core` is always on: the lookups plus `update_maps`, which the
/// daily loop needs. `map` holds the resolution and barrel diagnostics.
pub const GROUPS: &[(&str, &[&str])] = &[
    (
        "core",
        &[
            "session_bootstrap",
            "prepare_edit",
            "get_dependencies",
            "get_dependents",
            "get_file_wiki",
            "list_paths",
            "suggest_next_actions",
            "update_maps",
        ],
    ),
    (
        "notes",
        &[
            "record_change",
            "record_changes",
            "record_deletion",
            "search_journal",
            "why_file",
            "journal",
        ],
    ),
    (
        "health",
        &[
            "check_changes",
            "mark_green",
            "verify_wikis",
            "health",
            "validate",
            "list_healable_stubs",
            "heal_stubs",
            "seed_source_content_hashes",
        ],
    ),
    (
        "map",
        &[
            "get_resolution_diagnostics",
            "get_barrel_reports",
            "get_incremental_status",
        ],
    ),
    ("cycles", &["get_cycles"]),
    (
        "status",
        &[
            "list_core_tools",
            "get_project_status",
            "get_current_project_root",
            "issues",
            "get_files_needing_attention",
        ],
    ),
];

/// The group a tool belongs to.
pub fn group_of(tool: &str) -> Option<&'static str> {
    GROUPS
        .iter()
        .find(|(_, tools)| tools.contains(&tool))
        .map(|(group, _)| *group)
}

/// Where one key of a selection came from: the operator's environment or the agent's
/// `agent-tools` block in AGENTS.md.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Source {
    Env,
    AgentsMd,
}

/// Which tools the MCP surface exposes, and why the others are off.
#[derive(Clone, Debug)]
pub struct Selection {
    enabled: BTreeSet<&'static str>,
    tools: Option<(Vec<String>, Source)>,
    disable: Option<(Vec<String>, Source)>,
}

impl Selection {
    /// Every tool on: no switch and no block.
    pub fn all() -> Self {
        Selection {
            enabled: MCP_TOOLS.iter().copied().collect(),
            tools: None,
            disable: None,
        }
    }

    /// Read the two variables from the environment. A blank value counts as unset.
    pub fn from_env() -> Result<Self, String> {
        Self::parse(
            env_value(TOOLS_VAR).as_deref(),
            env_value(DISABLE_VAR).as_deref(),
        )
    }

    /// `tools` is the allowlist (`None` = every tool), `disable` is applied after it.
    /// Names are groups or tool names; case and whitespace are ignored, and a blank value
    /// is unset. `core` stays on: naming it, or one of its tools, in `disable` is an error.
    pub fn parse(tools: Option<&str>, disable: Option<&str>) -> Result<Self, String> {
        Self::resolve(tools, disable, &AgentTools::default()).map(|(selection, _)| selection)
    }

    /// The environment wins per key: `WIKIFIER_TOOLS` over the block's `tools` line and
    /// `WIKIFIER_DISABLE` over its `disable` line. An environment error is returned (the
    /// server exits 2). A block error is a warning: that line is ignored and the default
    /// applies to its key.
    pub fn resolve(
        env_tools: Option<&str>,
        env_disable: Option<&str>,
        block: &AgentTools,
    ) -> Result<(Self, Vec<String>), String> {
        let env_tools = env_tools.filter(|text| !text.trim().is_empty());
        let env_disable = env_disable.filter(|text| !text.trim().is_empty());
        let mut warnings = block.warnings.clone();
        let tools = match (env_tools, &block.tools) {
            (Some(text), _) => Some((
                split_names(text, true).map_err(|name| env_unknown(TOOLS_VAR, &name))?,
                Source::Env,
            )),
            (None, Some(text)) => match split_names(text, true) {
                Ok(list) => Some((list, Source::AgentsMd)),
                Err(name) => {
                    warnings.push(block_unknown(&name));
                    None
                }
            },
            (None, None) => None,
        };
        let disable = match (env_disable, &block.disable) {
            (Some(text), _) => {
                let list =
                    split_names(text, false).map_err(|name| env_unknown(DISABLE_VAR, &name))?;
                if let Some(name) = core_named(&list) {
                    return Err(format!(
                        "{DISABLE_VAR}: \"{name}\" cannot be disabled, group \"core\" is always on; groups: {}",
                        group_names().join(", ")
                    ));
                }
                Some((list, Source::Env))
            }
            (None, Some(text)) => match split_names(text, false) {
                Ok(list) => match core_named(&list) {
                    Some(name) => {
                        warnings.push(format!(
                            "AGENTS.md agent-tools: \"{name}\" cannot be disabled for wikifier, group \"core\" is always on; groups: {}",
                            group_names().join(", ")
                        ));
                        None
                    }
                    None => Some((list, Source::AgentsMd)),
                },
                Err(name) => {
                    warnings.push(block_unknown(&name));
                    None
                }
            },
            (None, None) => None,
        };
        let mut enabled: BTreeSet<&'static str> = match &tools {
            Some((list, _)) if !list.iter().any(|name| name == "all") => MCP_TOOLS
                .iter()
                .copied()
                .filter(|tool| matches(list, tool))
                .collect(),
            _ => MCP_TOOLS.iter().copied().collect(),
        };
        if let Some((list, _)) = &disable {
            enabled.retain(|tool| !matches(list, tool));
        }
        enabled.extend(core_tools());
        Ok((
            Selection {
                enabled,
                tools,
                disable,
            },
            warnings,
        ))
    }

    /// True when a switch or a block line shaped this selection.
    pub fn is_filtered(&self) -> bool {
        self.tools.is_some() || self.disable.is_some()
    }

    pub fn allows(&self, tool: &str) -> bool {
        self.enabled.contains(tool) || group_of(tool).is_none()
    }

    /// The exposed tools, for noticing that a block edit changed the list.
    pub fn enabled(&self) -> &BTreeSet<&'static str> {
        &self.enabled
    }

    /// The one-line error for calling a tool that is switched off.
    pub fn refusal(&self, tool: &str) -> String {
        let group = group_of(tool).unwrap_or("");
        if let Some((list, source)) = &self.disable {
            if let Some(name) = list
                .iter()
                .find(|name| name.as_str() == group || name.as_str() == tool)
            {
                return match source {
                    Source::Env => format!(
                        "tool \"{tool}\" is disabled (group \"{group}\") by {DISABLE_VAR}; remove \"{name}\" from it to enable"
                    ),
                    Source::AgentsMd => format!(
                        "tool \"{tool}\" is disabled (group \"{group}\") by AGENTS.md agent-tools; remove \"{name}\" from the \"wikifier: disable\" line to enable"
                    ),
                };
            }
        }
        match self.tools.as_ref().map(|(_, source)| *source) {
            Some(Source::AgentsMd) => format!(
                "tool \"{tool}\" is disabled (group \"{group}\") by AGENTS.md agent-tools; add \"{group}\" to the \"wikifier: tools\" line to enable"
            ),
            _ => format!(
                "tool \"{tool}\" is disabled (group \"{group}\") by {TOOLS_VAR}; add \"{group}\" to it to enable"
            ),
        }
    }

    /// Groups with at least one tool on, in table order.
    pub fn active_groups(&self) -> Vec<&'static str> {
        GROUPS
            .iter()
            .filter(|(_, tools)| tools.iter().any(|tool| self.enabled.contains(tool)))
            .map(|(group, _)| *group)
            .collect()
    }

    /// The closing line of the `initialize` instructions and of `list_core_tools`.
    pub fn summary(&self) -> String {
        let on = self.active_groups();
        let off: Vec<&str> = group_names()
            .into_iter()
            .filter(|group| !on.contains(group))
            .collect();
        format!(
            "Wikifier tool groups on: {}; off: {}. Change them with a \"wikifier: tools ...\" or \"wikifier: disable ...\" line in the agent-tools block of AGENTS.md ({TOOLS_VAR} / {DISABLE_VAR} override it).",
            on.join(", "),
            if off.is_empty() {
                "none".to_string()
            } else {
                off.join(", ")
            }
        )
    }
}

/// This tool's lines from the first fenced `agent-tools` block of an AGENTS.md.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct AgentTools {
    /// An `agent-tools` block exists, whether or not it has a wikifier line. A block inside
    /// another fence (a docs example) is text, not config.
    pub found: bool,
    pub tools: Option<String>,
    pub disable: Option<String>,
    pub warnings: Vec<String>,
}

impl AgentTools {
    /// Read the first fenced block whose info string is `agent-tools`. Lines for other
    /// tools are ignored; `#` starts a comment; lists take commas or spaces.
    pub fn parse(text: &str) -> Self {
        let mut out = AgentTools::default();
        let mut fence: Option<(char, usize, bool)> = None;
        for line in text.lines() {
            let trimmed = line.trim_start();
            let shallow = line.len() - trimmed.len() <= 3;
            if let Some((mark, len, ours)) = fence {
                if shallow && closes(trimmed, mark, len) {
                    if ours {
                        return out;
                    }
                    fence = None;
                } else if ours {
                    out.read_line(trimmed);
                }
                continue;
            }
            if shallow {
                if let Some((mark, len, info)) = opens(trimmed) {
                    let ours = info.split_whitespace().next() == Some("agent-tools");
                    out.found |= ours;
                    fence = Some((mark, len, ours));
                }
            }
        }
        out
    }

    fn read_line(&mut self, line: &str) {
        let line = line.split('#').next().unwrap_or("").trim();
        let Some((tool, rest)) = line.split_once(':') else {
            return;
        };
        if !tool.trim().eq_ignore_ascii_case("wikifier") {
            return;
        }
        let rest = rest.trim();
        let (key, list) = rest.split_once(char::is_whitespace).unwrap_or((rest, ""));
        let list = list
            .split(|c: char| c == ',' || c.is_whitespace())
            .filter(|name| !name.is_empty())
            .collect::<Vec<_>>()
            .join(",");
        let slot = match key.to_ascii_lowercase().as_str() {
            "tools" => &mut self.tools,
            "disable" => &mut self.disable,
            _ => {
                self.warnings.push(format!(
                    "AGENTS.md agent-tools: unknown key \"{key}\" for wikifier; write \"wikifier: tools <groups>\" or \"wikifier: disable <groups>\""
                ));
                return;
            }
        };
        match slot {
            Some(existing) if !list.is_empty() => {
                existing.push(',');
                existing.push_str(&list);
            }
            Some(_) => {}
            None => *slot = Some(list),
        }
    }
}

/// A fence opening: at least three backticks or tildes, then the info string.
fn opens(line: &str) -> Option<(char, usize, &str)> {
    let mark = line.chars().next().filter(|c| *c == '`' || *c == '~')?;
    let len = line.chars().take_while(|c| *c == mark).count();
    if len < 3 {
        return None;
    }
    let info = line[len..].trim();
    if mark == '`' && info.contains('`') {
        return None;
    }
    Some((mark, len, info))
}

fn closes(line: &str, mark: char, len: usize) -> bool {
    let line = line.trim_end();
    line.chars().count() >= len && line.chars().all(|c| c == mark)
}

fn env_value(key: &str) -> Option<String> {
    std::env::var(key).ok().filter(|v| !v.trim().is_empty())
}

fn env_unknown(var: &str, name: &str) -> String {
    format!(
        "{var}: unknown group \"{name}\"; groups: {}; tools: {}",
        group_names().join(", "),
        MCP_TOOLS.join(", ")
    )
}

fn block_unknown(name: &str) -> String {
    format!(
        "AGENTS.md agent-tools: unknown group \"{name}\" for wikifier; groups: {}",
        group_names().join(", ")
    )
}

fn core_named(list: &[String]) -> Option<&String> {
    list.iter()
        .find(|name| name.as_str() == "core" || group_of(name) == Some("core"))
}

fn group_names() -> Vec<&'static str> {
    GROUPS.iter().map(|(group, _)| *group).collect()
}

fn core_tools() -> impl Iterator<Item = &'static str> {
    GROUPS
        .iter()
        .filter(|(group, _)| *group == "core")
        .flat_map(|(_, tools)| tools.iter().copied())
}

fn matches(list: &[String], tool: &str) -> bool {
    let group = group_of(tool).unwrap_or("");
    list.iter().any(|name| name == tool || name == group)
}

/// Split on commas, trim, and lowercase; `Err` carries the first name that is no group or
/// tool (`all` only where it is allowed).
fn split_names(text: &str, allow_all: bool) -> Result<Vec<String>, String> {
    let mut out = Vec::new();
    for raw in text.split(',') {
        let name = raw.trim().to_ascii_lowercase();
        if name.is_empty() {
            continue;
        }
        let known = (allow_all && name == "all")
            || GROUPS.iter().any(|(group, _)| *group == name)
            || MCP_TOOLS.contains(&name.as_str());
        if !known {
            return Err(name);
        }
        out.push(name);
    }
    Ok(out)
}
