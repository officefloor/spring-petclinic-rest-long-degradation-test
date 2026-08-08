package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** membership-number: the YY segment uses the business-day-adjusted
 * registration date. Supplying a Saturday whose Monday roll stays in the same year, the YY still
 * matches the returned (adjusted) registrationDate's year. */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreYearSegmentFromAdjustedDate() throws Exception {
		ObjectNode o = ownerNode();
		o.put("registrationDate", "2026-01-03"); // Saturday -> Monday 2026-01-05
		JsonNode r = fetchOwner(createOwnerOk(o));
		String yy = r.get("registrationDate").asText().substring(2, 4);
		assertTrue(r.get("membershipNumber").asText().endsWith("-M" + yy),
				r.get("membershipNumber").asText());
	}
}
