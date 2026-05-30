import type { DocsGroup, DocsPage } from "@/lib/docsNav";

export type Heading = {
  level: 2 | 3;
  text: string;
  id: string;
};

export type TocNode = {
  heading: Heading;
  children: Heading[];
};

export type DocsSearchResult = {
  groupId: DocsGroup["id"];
  groupLabel: string;
  pageId: string;
  pageTitle: string;
  heading: string | null;
  anchor: string | null;
  snippet: string;
  score: number;
};

type SearchSection = {
  page: DocsPage;
  pageIndex: number;
  sectionIndex: number;
  heading: string | null;
  anchor: string | null;
  text: string;
};

const MAX_SEARCH_RESULTS = 64;
const SNIPPET_RADIUS = 96;

export function slugify(text: string): string {
  return text
    .replace(/<[^>]*>/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function extractHeadings(markdown: string): Heading[] {
  const headings: Heading[] = [];
  for (const line of markdown.split("\n")) {
    const h2 = line.match(/^##\s+(.+)$/);
    const h3 = line.match(/^###\s+(.+)$/);
    if (h2) headings.push({ level: 2, text: h2[1].trim(), id: slugify(h2[1]) });
    if (h3) headings.push({ level: 3, text: h3[1].trim(), id: slugify(h3[1]) });
  }
  return headings;
}

export function buildTocTree(headings: Heading[]): TocNode[] {
  const tree: TocNode[] = [];
  let current: TocNode | null = null;
  for (const heading of headings) {
    if (heading.level === 2) {
      current = { heading, children: [] };
      tree.push(current);
    } else if (current) {
      current.children.push(heading);
    }
  }
  return tree;
}

export function tokenizeSearchQuery(query: string): string[] {
  const unique = new Set<string>();
  for (const token of query.toLowerCase().match(/[a-z0-9_.:/-]+/g) ?? []) {
    if (token.length >= 2) unique.add(token);
  }
  return Array.from(unique).sort((left, right) => right.length - left.length);
}

export function buildDocsSearchResults(
  groups: DocsGroup[],
  preferredGroupId: DocsGroup["id"],
  query: string,
  limit = MAX_SEARCH_RESULTS,
): DocsSearchResult[] {
  const terms = tokenizeSearchQuery(query);
  if (terms.length === 0) return [];

  const phrase = query.trim().toLowerCase();
  const results: Array<
    DocsSearchResult & {
      groupIndex: number;
      groupPriority: number;
      pageIndex: number;
      sectionIndex: number;
    }
  > = [];

  groups.forEach((group, groupIndex) => {
    group.pages.forEach((page, pageIndex) => {
      buildPageSections(page, pageIndex).forEach((section) => {
        const score = scoreSection(section, terms, phrase);
        if (score <= 0) return;
        results.push({
          groupId: group.id,
          groupLabel: group.label,
          pageId: page.id,
          pageTitle: page.title,
          heading: section.heading,
          anchor: section.anchor,
          snippet: createSnippet(section.text || page.content, terms),
          score,
          groupIndex,
          groupPriority: group.id === preferredGroupId ? 0 : 1,
          pageIndex,
          sectionIndex: section.sectionIndex,
        });
      });
    });
  });

  return results
    .sort((left, right) => {
      if (left.groupPriority !== right.groupPriority) {
        return left.groupPriority - right.groupPriority;
      }
      if (right.score !== left.score) return right.score - left.score;
      if (left.groupIndex !== right.groupIndex) return left.groupIndex - right.groupIndex;
      if (left.pageIndex !== right.pageIndex) return left.pageIndex - right.pageIndex;
      return left.sectionIndex - right.sectionIndex;
    })
    .slice(0, limit)
    .map(
      ({
        groupIndex: _groupIndex,
        groupPriority: _groupPriority,
        pageIndex: _pageIndex,
        sectionIndex: _sectionIndex,
        ...result
      }) => result,
    );
}

function buildPageSections(page: DocsPage, pageIndex: number): SearchSection[] {
  const sections: SearchSection[] = [
    {
      page,
      pageIndex,
      sectionIndex: 0,
      heading: null,
      anchor: null,
      text: "",
    },
  ];
  let current = sections[0];

  for (const line of page.content.replace(/\r\n/g, "\n").split("\n")) {
    const trimmed = line.trim();
    const heading = trimmed.match(/^(#{2,3})\s+(.+)$/);
    if (heading) {
      const rawHeadingText = heading[2].trim();
      const headingText = stripMarkdown(rawHeadingText);
      current = {
        page,
        pageIndex,
        sectionIndex: sections.length,
        heading: headingText,
        anchor: slugify(rawHeadingText),
        text: "",
      };
      sections.push(current);
      continue;
    }

    if (trimmed.startsWith("```") || trimmed === "$$") {
      continue;
    }

    const text = stripMarkdown(trimmed);
    if (text) {
      current.text = `${current.text} ${text}`.trim();
    }
  }

  return sections;
}

function scoreSection(section: SearchSection, terms: string[], phrase: string): number {
  const pageTitle = section.page.title.toLowerCase();
  const heading = section.heading?.toLowerCase() ?? "";
  const body = section.text.toLowerCase();
  let score = 0;

  for (const term of terms) {
    score += countOccurrences(pageTitle, term) * 90;
    score += countOccurrences(heading, term) * 55;
    score += countOccurrences(body, term) * 8;
  }

  if (phrase.length > 1) {
    if (pageTitle.includes(phrase)) score += 160;
    if (heading.includes(phrase)) score += 100;
    if (body.includes(phrase)) score += 32;
  }

  if (section.anchor === null && score > 0) score += 12;
  return score;
}

function countOccurrences(text: string, term: string): number {
  if (!text || !term) return 0;
  let count = 0;
  let index = text.indexOf(term);
  while (index !== -1) {
    count += 1;
    index = text.indexOf(term, index + term.length);
  }
  return count;
}

function createSnippet(text: string, terms: string[]): string {
  const collapsed = stripMarkdown(text).replace(/\s+/g, " ").trim();
  if (!collapsed) return "";

  const lower = collapsed.toLowerCase();
  const hit = terms
    .map((term) => lower.indexOf(term))
    .filter((index) => index >= 0)
    .sort((left, right) => left - right)[0];

  if (hit === undefined) {
    return trimSnippet(collapsed.slice(0, SNIPPET_RADIUS * 2), 0, collapsed.length);
  }

  const start = Math.max(0, hit - SNIPPET_RADIUS);
  const end = Math.min(collapsed.length, hit + SNIPPET_RADIUS);
  return trimSnippet(collapsed.slice(start, end), start, collapsed.length);
}

function trimSnippet(snippet: string, start: number, fullLength: number): string {
  let trimmed = snippet.trim();
  if (start > 0) {
    trimmed = trimmed.replace(/^\S+\s+/, "");
    trimmed = `...${trimmed}`;
  }
  if (start + snippet.length < fullLength) {
    trimmed = trimmed.replace(/\s+\S*$/, "");
    trimmed = `${trimmed}...`;
  }
  return trimmed;
}

function stripMarkdown(text: string): string {
  return text
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/, "")
    .replace(/^\s{0,3}>\s?/, "")
    .replace(/^\s*[-*+]\s+/, "")
    .replace(/^\s*\d+\.\s+/, "")
    .replace(/\|/g, " ")
    .replace(/[*_~]/g, "")
    .replace(/\$+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
