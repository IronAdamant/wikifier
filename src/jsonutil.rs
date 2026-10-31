//! JSON subset for our own shapes, `package.json`, and comment-stripped tsconfig.

use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    String(String),
    Array(Vec<Json>),
    Object(BTreeMap<String, Json>),
}

impl Json {
    pub fn obj(pairs: Vec<(&str, Json)>) -> Json {
        let mut m = BTreeMap::new();
        for (k, v) in pairs {
            m.insert(k.to_string(), v);
        }
        Json::Object(m)
    }

    pub fn from_pairs(pairs: Vec<(String, Json)>) -> Json {
        Json::Object(pairs.into_iter().collect())
    }

    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Object(m) => m.get(key),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Json::String(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Json::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Json]> {
        match self {
            Json::Array(a) => Some(a),
            _ => None,
        }
    }

    pub fn as_object(&self) -> Option<&BTreeMap<String, Json>> {
        match self {
            Json::Object(m) => Some(m),
            _ => None,
        }
    }

    pub fn insert(&mut self, key: &str, value: Json) {
        if let Json::Object(m) = self {
            m.insert(key.to_string(), value);
        }
    }
}

impl std::fmt::Display for Json {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Json::Null => write!(f, "null"),
            Json::Bool(true) => write!(f, "true"),
            Json::Bool(false) => write!(f, "false"),
            Json::Int(n) => write!(f, "{n}"),
            Json::Float(n) => {
                if n.is_finite() {
                    let s = format!("{n}");
                    if s.contains('.') || s.contains('e') || s.contains('E') {
                        write!(f, "{s}")
                    } else {
                        write!(f, "{s}.0")
                    }
                } else {
                    write!(f, "null")
                }
            }
            Json::String(s) => write!(f, "\"{}\"", escape(s)),
            Json::Array(a) => {
                write!(f, "[")?;
                for (i, v) in a.iter().enumerate() {
                    if i > 0 {
                        write!(f, ",")?;
                    }
                    write!(f, "{v}")?;
                }
                write!(f, "]")
            }
            Json::Object(m) => {
                write!(f, "{{")?;
                for (i, (k, v)) in m.iter().enumerate() {
                    if i > 0 {
                        write!(f, ",")?;
                    }
                    write!(f, "\"{}\":{v}", escape(k))?;
                }
                write!(f, "}}")
            }
        }
    }
}

fn escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

pub fn parse(input: &str) -> Result<Json, String> {
    let mut p = Parser { s: input.as_bytes(), i: 0 };
    let v = p.value()?;
    p.skip();
    if p.i != p.s.len() {
        return Err("trailing json".into());
    }
    Ok(v)
}

/// Drop `//` and `/* */` comments that sit outside strings, then parse.
pub fn parse_jsonc(input: &str) -> Result<Json, String> {
    parse(&strip_json_comments(input))
}

pub fn strip_json_comments(input: &str) -> String {
    let b = input.as_bytes();
    let mut out = Vec::with_capacity(input.len());
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'"' {
            let start = i;
            i += 1;
            while i < b.len() {
                if b[i] == b'\\' && i + 1 < b.len() {
                    i += 2;
                    continue;
                }
                if b[i] == b'"' {
                    i += 1;
                    break;
                }
                i += 1;
            }
            out.extend_from_slice(&b[start..i]);
            continue;
        }
        if b[i] == b'/' && i + 1 < b.len() && b[i + 1] == b'/' {
            i += 2;
            while i < b.len() && b[i] != b'\n' {
                i += 1;
            }
            continue;
        }
        if b[i] == b'/' && i + 1 < b.len() && b[i + 1] == b'*' {
            i += 2;
            while i + 1 < b.len() && !(b[i] == b'*' && b[i + 1] == b'/') {
                i += 1;
            }
            i = (i + 2).min(b.len());
            continue;
        }
        out.push(b[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
}

impl<'a> Parser<'a> {
    fn skip(&mut self) {
        while self.i < self.s.len() && self.s[self.i].is_ascii_whitespace() {
            self.i += 1;
        }
    }
    fn value(&mut self) -> Result<Json, String> {
        self.skip();
        if self.i >= self.s.len() {
            return Err("unexpected end".into());
        }
        match self.s[self.i] {
            b'n' => self.lit(b"null", Json::Null),
            b't' => self.lit(b"true", Json::Bool(true)),
            b'f' => self.lit(b"false", Json::Bool(false)),
            b'"' => Ok(Json::String(self.string()?)),
            b'[' => self.array(),
            b'{' => self.object(),
            b'-' | b'0'..=b'9' => self.number(),
            c => Err(format!("bad json byte {c}")),
        }
    }
    fn lit(&mut self, expect: &[u8], v: Json) -> Result<Json, String> {
        if self.s[self.i..].starts_with(expect) {
            self.i += expect.len();
            Ok(v)
        } else {
            Err("bad literal".into())
        }
    }
    fn string(&mut self) -> Result<String, String> {
        self.i += 1;
        let mut out: Vec<u8> = Vec::new();
        while self.i < self.s.len() {
            let c = self.s[self.i];
            self.i += 1;
            match c {
                b'"' => return String::from_utf8(out).map_err(|e| e.to_string()),
                b'\\' => {
                    if self.i >= self.s.len() {
                        return Err("bad escape".into());
                    }
                    let e = self.s[self.i];
                    self.i += 1;
                    match e {
                        b'"' => out.push(b'"'),
                        b'\\' => out.push(b'\\'),
                        b'/' => out.push(b'/'),
                        b'n' => out.push(b'\n'),
                        b'r' => out.push(b'\r'),
                        b't' => out.push(b'\t'),
                        b'u' => {
                            if self.i + 4 > self.s.len() {
                                return Err("bad unicode".into());
                            }
                            let hex = std::str::from_utf8(&self.s[self.i..self.i + 4]).map_err(|e| e.to_string())?;
                            let cp = u32::from_str_radix(hex, 16).map_err(|e| e.to_string())?;
                            let ch = char::from_u32(cp).unwrap_or('\u{FFFD}');
                            let mut buf = [0u8; 4];
                            out.extend_from_slice(ch.encode_utf8(&mut buf).as_bytes());
                            self.i += 4;
                        }
                        _ => return Err("bad escape".into()),
                    }
                }
                c => out.push(c),
            }
        }
        Err("unterminated string".into())
    }
    fn number(&mut self) -> Result<Json, String> {
        let start = self.i;
        if self.s[self.i] == b'-' {
            self.i += 1;
        }
        while self.i < self.s.len() && self.s[self.i].is_ascii_digit() {
            self.i += 1;
        }
        let mut float = false;
        if self.i < self.s.len() && self.s[self.i] == b'.' {
            float = true;
            self.i += 1;
            while self.i < self.s.len() && self.s[self.i].is_ascii_digit() {
                self.i += 1;
            }
        }
        if self.i < self.s.len() && (self.s[self.i] == b'e' || self.s[self.i] == b'E') {
            float = true;
            self.i += 1;
            if self.i < self.s.len() && (self.s[self.i] == b'+' || self.s[self.i] == b'-') {
                self.i += 1;
            }
            while self.i < self.s.len() && self.s[self.i].is_ascii_digit() {
                self.i += 1;
            }
        }
        let text = std::str::from_utf8(&self.s[start..self.i]).map_err(|e| e.to_string())?;
        if float {
            text.parse::<f64>().map(Json::Float).map_err(|e| e.to_string())
        } else {
            text.parse::<i64>().map(Json::Int).map_err(|e| e.to_string())
        }
    }
    fn array(&mut self) -> Result<Json, String> {
        self.i += 1;
        let mut items = Vec::new();
        self.skip();
        if self.i < self.s.len() && self.s[self.i] == b']' {
            self.i += 1;
            return Ok(Json::Array(items));
        }
        loop {
            items.push(self.value()?);
            self.skip();
            if self.i >= self.s.len() {
                return Err("unterminated array".into());
            }
            if self.s[self.i] == b']' {
                self.i += 1;
                break;
            }
            if self.s[self.i] != b',' {
                return Err("expected comma".into());
            }
            self.i += 1;
        }
        Ok(Json::Array(items))
    }
    fn object(&mut self) -> Result<Json, String> {
        self.i += 1;
        let mut map = BTreeMap::new();
        self.skip();
        if self.i < self.s.len() && self.s[self.i] == b'}' {
            self.i += 1;
            return Ok(Json::Object(map));
        }
        loop {
            self.skip();
            if self.i >= self.s.len() || self.s[self.i] != b'"' {
                return Err("expected key".into());
            }
            let key = self.string()?;
            self.skip();
            if self.i >= self.s.len() || self.s[self.i] != b':' {
                return Err("expected colon".into());
            }
            self.i += 1;
            map.insert(key, self.value()?);
            self.skip();
            if self.i >= self.s.len() {
                return Err("unterminated object".into());
            }
            if self.s[self.i] == b'}' {
                self.i += 1;
                break;
            }
            if self.s[self.i] != b',' {
                return Err("expected comma".into());
            }
            self.i += 1;
        }
        Ok(Json::Object(map))
    }
}
