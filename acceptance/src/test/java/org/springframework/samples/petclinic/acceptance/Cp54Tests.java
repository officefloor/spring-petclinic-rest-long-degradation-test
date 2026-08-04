package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp54 capacity-warning: Return 'capacityWarning' true when the owner's city already has between 40 and 49 owners (... */
@Tag("cp54")
class Cp54Tests extends AcceptanceBase {

	@Test
	void coreCapacityWarningFalseNormally() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.capacityWarning").value(false)); // TODO: true at 40-49
	}
}
