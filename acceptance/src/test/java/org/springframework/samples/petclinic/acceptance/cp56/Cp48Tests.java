package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** fiscal-year: fiscalYear remains an 'FY<YY>' field (its 2-digit year is now
 * also embedded in the memberId). */
@Tag("cp48")
class Cp48Tests extends AcceptanceBase {

	@Test
	void coreFiscalYearPresent() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney")));
		assertTrue(r.get("fiscalYear").asText().matches("FY\\d{2}"), r.get("fiscalYear").asText());
	}
}
