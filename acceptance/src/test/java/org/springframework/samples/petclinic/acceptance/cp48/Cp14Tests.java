package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** membership-number: the '-M<YY>' segment now uses the fiscal year (FY<YY>)
 * rather than the calendar year. The YY must match the returned fiscalYear. */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreYearSegmentIsFiscal() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney")));
		String fy = r.get("fiscalYear").asText().substring(2); // FY26 -> 26
		assertTrue(r.get("membershipNumber").asText().endsWith("-M" + fy),
				r.get("membershipNumber").asText() + " / " + r.get("fiscalYear").asText());
	}
}
