/** Sheldon grade numbers and the letter grade each belongs to (2 is FR, 45 XF, 63 MS). */
export const GRADE_NUMBERS: [string, number[]][] = [
  ["PO", [1]], ["FR", [2]], ["AG", [3]], ["G", [4, 6]], ["VG", [8, 10]], ["F", [12, 15]], ["VF", [20, 25, 30, 35]],
  ["XF", [40, 45]], ["AU", [50, 53, 55, 58]], ["MS", [60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70]],
];
export const SHELDON_NUMBERS = GRADE_NUMBERS.flatMap(([, ns]) => ns);
export const letterGrade = (n: number) => GRADE_NUMBERS.find(([, ns]) => ns.includes(n))?.[0] ?? "MS";
