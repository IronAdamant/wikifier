//! Read a git checkout's index (`.git/index`, versions 2 and 3) without running git.
//!
//! A worktree overlay uses it to prove a file unchanged without reading it: when a file's
//! size and mtime still match its index entry, git vouches that its bytes are that entry's
//! blob. Two checkouts whose entries for a path carry the same blob id hold the same bytes.
//! A fresh `git worktree add` has new mtimes on every file, so without this the first
//! overlay call read and hashed the whole tree (7 s of a 10 s call on Specula).
//!
//! Anything this reader does not understand (index v4, a split index, a truncated file)
//! yields `None`, and the caller hashes the files as before.

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

struct Entry {
    mtime: (u32, u32),
    size: u32,
    oid: Vec<u8>,
}

pub(crate) struct GitIndex {
    entries: HashMap<String, Entry>,
    /// The index file's own mtime. An entry stamped at or after it is "racily clean": the
    /// file may have changed in the same tick, so it proves nothing.
    written: (u32, u32),
}

/// The git dir of a checkout: `.git` itself, or the `gitdir:` its `.git` file names.
fn git_dir(checkout: &Path) -> Option<PathBuf> {
    let dot = checkout.join(".git");
    if dot.is_dir() {
        return Some(dot);
    }
    let text = fs::read_to_string(&dot).ok()?;
    let gitdir = text
        .lines()
        .find_map(|l| l.trim().strip_prefix("gitdir:"))?;
    Some(checkout.join(gitdir.trim()))
}

/// 20 for SHA-1 repositories, 32 for `extensions.objectFormat = sha256`.
fn oid_len(git_dir: &Path) -> usize {
    let common = match fs::read_to_string(git_dir.join("commondir")) {
        Ok(rel) => git_dir.join(rel.trim()),
        Err(_) => git_dir.to_path_buf(),
    };
    let config = fs::read_to_string(common.join("config")).unwrap_or_default();
    let sha256 = config.lines().any(|line| {
        let line = line.trim().to_ascii_lowercase().replace(' ', "");
        line == "objectformat=sha256"
    });
    if sha256 {
        32
    } else {
        20
    }
}

fn be32(data: &[u8], at: usize) -> Option<u32> {
    let bytes = data.get(at..at + 4)?;
    Some(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
}

fn be16(data: &[u8], at: usize) -> Option<u16> {
    let bytes = data.get(at..at + 2)?;
    Some(u16::from_be_bytes([bytes[0], bytes[1]]))
}

fn mtime_of(meta: &fs::Metadata) -> Option<(u32, u32)> {
    let since = meta.modified().ok()?.duration_since(UNIX_EPOCH).ok()?;
    Some((since.as_secs() as u32, since.subsec_nanos()))
}

/// Same instant as git records it: seconds always; nanoseconds only when git stored them
/// (a build without nanosecond stamps writes 0 and compares seconds alone).
fn same_time(stamp: (u32, u32), file: (u32, u32)) -> bool {
    stamp.0 == file.0 && (stamp.1 == 0 || stamp.1 == file.1)
}

fn at_or_after(stamp: (u32, u32), written: (u32, u32)) -> bool {
    if stamp.1 == 0 || written.1 == 0 {
        stamp.0 >= written.0
    } else {
        stamp >= written
    }
}

impl GitIndex {
    pub(crate) fn read(checkout: &Path) -> Option<GitIndex> {
        let dir = git_dir(checkout)?;
        let path = dir.join("index");
        let written = mtime_of(&fs::metadata(&path).ok()?)?;
        let data = fs::read(&path).ok()?;
        GitIndex::parse(&data, oid_len(&dir), written)
    }

    fn parse(data: &[u8], oid_len: usize, written: (u32, u32)) -> Option<GitIndex> {
        if data.get(..4)? != b"DIRC" {
            return None;
        }
        let version = be32(data, 4)?;
        if !(2..=3).contains(&version) {
            return None;
        }
        let count = be32(data, 8)? as usize;
        let mut entries = HashMap::with_capacity(count);
        let mut pos = 12;
        for _ in 0..count {
            let mtime = (be32(data, pos + 8)?, be32(data, pos + 12)?);
            let size = be32(data, pos + 36)?;
            let oid = data.get(pos + 40..pos + 40 + oid_len)?.to_vec();
            let flags = be16(data, pos + 40 + oid_len)?;
            let mut name_at = pos + 40 + oid_len + 2;
            if flags & 0x4000 != 0 {
                if version < 3 {
                    return None;
                }
                name_at += 2;
            }
            let short = (flags & 0x0fff) as usize;
            let name_len = if short < 0x0fff {
                short
            } else {
                data.get(name_at..)?.iter().position(|b| *b == 0)?
            };
            let name = std::str::from_utf8(data.get(name_at..name_at + name_len)?).ok()?;
            let stage = (flags >> 12) & 0x3;
            if stage == 0 {
                entries.insert(name.to_string(), Entry { mtime, size, oid });
            }
            // On-disk entries are NUL-padded to a multiple of 8 bytes, with at least one NUL.
            pos += (name_at - pos + name_len + 8) & !7;
        }
        Some(GitIndex { entries, written })
    }

    /// The blob id git recorded for `rel`, when the file at `path` still has that entry's
    /// size and mtime and the entry is not racily clean. `None` proves nothing.
    pub(crate) fn blob_if_fresh(&self, rel: &str, path: &Path) -> Option<&[u8]> {
        let entry = self.entries.get(rel)?;
        if at_or_after(entry.mtime, self.written) {
            return None;
        }
        let meta = fs::metadata(path).ok()?;
        if meta.len() as u32 != entry.size || !same_time(entry.mtime, mtime_of(&meta)?) {
            return None;
        }
        Some(&entry.oid)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(name: &str, mtime: (u32, u32), size: u32, oid: u8, extended: bool) -> Vec<u8> {
        let mut out = Vec::new();
        for value in [0, 0, mtime.0, mtime.1, 0, 0, 0o100644, 0, 0, size] {
            out.extend_from_slice(&u32::to_be_bytes(value));
        }
        out.extend_from_slice(&[oid; 20]);
        let mut flags = name.len() as u16;
        if extended {
            flags |= 0x4000;
        }
        out.extend_from_slice(&flags.to_be_bytes());
        if extended {
            out.extend_from_slice(&[0, 0]);
        }
        let start = 40 + 20 + 2 + if extended { 2 } else { 0 };
        out.extend_from_slice(name.as_bytes());
        let total = (start + name.len() + 8) & !7;
        out.resize(total, 0);
        out
    }

    fn index(version: u32, entries: &[Vec<u8>]) -> Vec<u8> {
        let mut out = b"DIRC".to_vec();
        out.extend_from_slice(&version.to_be_bytes());
        out.extend_from_slice(&(entries.len() as u32).to_be_bytes());
        for e in entries {
            out.extend_from_slice(e);
        }
        out.extend_from_slice(&[0; 20]);
        out
    }

    #[test]
    fn parses_v2_and_v3_entries_and_skips_nothing_it_understands() {
        let data = index(
            2,
            &[
                entry("src/a.rs", (100, 5), 10, 1, false),
                entry("src/longer_name.rs", (101, 0), 20, 2, false),
            ],
        );
        let parsed = GitIndex::parse(&data, 20, (200, 0)).unwrap();
        assert_eq!(parsed.entries.len(), 2);
        assert_eq!(parsed.entries["src/a.rs"].size, 10);
        assert_eq!(parsed.entries["src/longer_name.rs"].oid, vec![2; 20]);
        let v3 = index(
            3,
            &[
                entry("x.rs", (1, 1), 3, 7, true),
                entry("y.rs", (1, 1), 4, 8, false),
            ],
        );
        let parsed = GitIndex::parse(&v3, 20, (200, 0)).unwrap();
        assert_eq!(parsed.entries["y.rs"].oid, vec![8; 20]);
        // v4 (path compression) and garbage are not understood: the caller hashes instead.
        assert!(GitIndex::parse(&index(4, &[]), 20, (0, 0)).is_none());
        assert!(GitIndex::parse(b"nope", 20, (0, 0)).is_none());
        assert!(GitIndex::parse(&data[..40], 20, (0, 0)).is_none());
    }

    #[test]
    fn racily_clean_entries_and_second_only_stamps() {
        assert!(at_or_after((5, 0), (5, 9)));
        assert!(!at_or_after((4, 9), (5, 0)));
        assert!(at_or_after((5, 9), (5, 9)));
        assert!(!at_or_after((5, 8), (5, 9)));
        assert!(same_time((5, 0), (5, 123)));
        assert!(!same_time((5, 7), (5, 123)));
        assert!(!same_time((4, 0), (5, 0)));
    }
}
