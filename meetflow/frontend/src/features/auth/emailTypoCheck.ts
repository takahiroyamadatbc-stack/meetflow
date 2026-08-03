/**
 * サインアップ時のメールアドレスタイポ検知（Issue #106）。
 * 著名メールドメインとの編集距離（Levenshtein距離）が近い場合に
 * 「もしかして◯◯ですか？」の提案を返す純粋関数。送信をブロックする
 * ものではなく、あくまで気づきのための警告表示に使う想定。
 */

/**
 * 対象ドメインリストはIssue #106での検討結果。
 * me.com/aol.com/msn.comは、ドメイン名部分が短く編集距離ベースの判定では
 * 無関係な短いドメインを誤検知しやすい上、日本向けアプリでの実利用者も
 * ほぼ見込めないため除外した。
 */
const KNOWN_EMAIL_DOMAINS = [
  "gmail.com",
  "yahoo.com",
  "hotmail.com",
  "outlook.com",
  "live.com",
  "icloud.com",
  "yahoo.co.jp",
  "outlook.jp",
  "live.jp",
  "docomo.ne.jp",
  "ezweb.ne.jp",
  "au.com",
  "softbank.ne.jp",
  "ymobile.ne.jp",
  "i.softbank.jp",
] as const;

/**
 * ドメイン名部分（最初のラベル、例："au.com"なら"au"）がこの文字数以下の
 * 候補は、通常の閾値（編集距離2）だと無関係な短いドメイン（例："bu.com"、
 * "eu.com"）を誤って拾いやすいため、より厳しい閾値（編集距離1かつ同じ
 * 文字数）を個別適用する。この結果、au.com等は依然として近い無関係な
 * ドメインを提案してしまう可能性が残るが、Issue #106での検討の結果、
 * 実用上許容できるトレードオフとして受け入れている。
 */
const SHORT_DOMAIN_NAME_LENGTH_THRESHOLD = 3;
const NORMAL_DISTANCE_THRESHOLD = 2;
const SHORT_DOMAIN_DISTANCE_THRESHOLD = 1;

function levenshteinDistance(a: string, b: string): number {
  let previousRow = Array.from({ length: b.length + 1 }, (_, j) => j);

  for (let i = 1; i <= a.length; i++) {
    const currentRow = [i];
    for (let j = 1; j <= b.length; j++) {
      const substitutionCost = a[i - 1] === b[j - 1] ? 0 : 1;
      currentRow.push(
        Math.min(
          currentRow[j - 1] + 1,
          previousRow[j] + 1,
          previousRow[j - 1] + substitutionCost,
        ),
      );
    }
    previousRow = currentRow;
  }

  return previousRow[b.length];
}

function domainNameLength(domain: string): number {
  return domain.split(".")[0].length;
}

/**
 * 入力メールアドレスが著名ドメインの典型的なタイポらしい場合、修正候補の
 * メールアドレスを返す。タイポらしくない場合（既に既知ドメインと一致、
 * どの候補とも十分近くない、複数候補と同着で判別できない等）はnullを返す。
 */
export function suggestEmailCorrection(email: string): string | null {
  const atIndex = email.lastIndexOf("@");
  if (atIndex <= 0 || atIndex === email.length - 1) {
    return null;
  }

  const localPart = email.slice(0, atIndex);
  const domain = email.slice(atIndex + 1).toLowerCase();

  if ((KNOWN_EMAIL_DOMAINS as readonly string[]).includes(domain)) {
    return null;
  }

  let bestCandidate: string | null = null;
  let bestDistance = Infinity;
  let isTie = false;

  for (const candidate of KNOWN_EMAIL_DOMAINS) {
    const isShortDomain = domainNameLength(candidate) <= SHORT_DOMAIN_NAME_LENGTH_THRESHOLD;
    if (isShortDomain && domain.length !== candidate.length) {
      continue;
    }

    const distance = levenshteinDistance(domain, candidate);
    const threshold = isShortDomain ? SHORT_DOMAIN_DISTANCE_THRESHOLD : NORMAL_DISTANCE_THRESHOLD;
    if (distance === 0 || distance > threshold) {
      continue;
    }

    if (distance < bestDistance) {
      bestDistance = distance;
      bestCandidate = candidate;
      isTie = false;
    } else if (distance === bestDistance) {
      isTie = true;
    }
  }

  if (!bestCandidate || isTie) {
    return null;
  }

  return `${localPart}@${bestCandidate}`;
}
