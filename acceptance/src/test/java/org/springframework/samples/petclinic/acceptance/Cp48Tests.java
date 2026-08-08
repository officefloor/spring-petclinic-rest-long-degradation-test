package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** fiscal-year: Move date-derived values to a fiscal-year basis, where the fiscal year starts on 1 July. R... */
@Tag("cp48")
class Cp48Tests extends AcceptanceBase {

	@Test
	void coreReturnsFiscalYear() throws Exception {
		int id = createOwnerOk(structuredOwner());
		JsonNode n = fetchOwner(id);
		assertTrue(n.get("fiscalYear").asText().matches("FY\\d{2}"));
	}
}
