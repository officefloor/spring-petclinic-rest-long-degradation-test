package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** locality-postcode: locality reads the structured postcode. A Sydney owner
 * with postcode 2000 resolves locality "NSW". */
@Tag("cp30")
class Cp30Tests extends AcceptanceBase {

	@Test
	void coreLocalityFromStructuredPostcode() throws Exception {
		ObjectNode o = structuredOwner();
		o.put("city", "Sydney");
		o.put("postcode", "2000");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.locality").value("NSW"));
	}
}
