package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** address-structured: structured addressLine1/city/postcode is accepted and normalized (
 * rules: upper-case, collapse whitespace, expand ST->STREET), and 'address' is the composed
 * normalized string. The flat 'address' form stays accepted (backward-compatible). */
@Tag("cp44")
class Cp44Tests extends AcceptanceBase {

	@Test
	void coreNormalizesAndComposesStructuredAddress() throws Exception {
		ObjectNode o = structuredOwner();
		o.put("addressLine1", "10 king st");
		o.remove("addressLine2");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.addressLine1").value("10 KING STREET"))
				.andExpect(jsonPath("$.address").value("10 KING STREET"));
	}

	@Test
	void functionalityStillAcceptsFlatAddress() throws Exception {
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}
}
